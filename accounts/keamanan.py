"""Hacking Activity, IP blacklist and maintenance mode (superuser menus).

- KeamananMiddleware (first in line): refuses a blacklisted address (IpBlokir)
  before anything else runs, and logs a request that looks like an attack
  (AktivitasMencurigakan): probing for well-known holes, SQL injection or XSS
  in the URL, a hacking tool's user agent. An address that keeps attacking is
  blocked by itself for BLOKIR_OTOMATIS.
- catat(): the other events (failed and locked logins, /admin by someone not
  allowed, CSRF failures, Daftar spam) logged from where they happen.
- PemeliharaanMiddleware: while maintenance is on, everyone but a superuser
  gets the maintenance page (503).

New events reach an open Hacking Activity page at once (realtime "keamanan").
"""
import datetime
import ipaddress
import re
import time
from urllib.parse import unquote_plus

from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .batas_login import ip_klien

# How long events are kept, and when an address blocks itself.
SIMPAN_HARI = 90
JENDELA_OTOMATIS = datetime.timedelta(minutes=10)
BATAS_TINGGI = 5  # high-severity events in the window
BATAS_SEMUA = 30  # any events in the window
BLOKIR_OTOMATIS = datetime.timedelta(hours=24)
# Never blocked by themselves: the server itself, and KEAMANAN_IP_AMAN in the
# environment (comma-separated: an office, the admins).
TIDAK_DIBLOKIR_OTOMATIS = {"127.0.0.1", "::1"} | {
    a.strip() for a in __import__("os").environ.get("KEAMANAN_IP_AMAN", "").split(",") if a.strip()
}

# The container networks (KEAMANAN_JARINGAN_PROXY, podman's defaults). Rootless
# podman hands nginx its connections from the network's gateway, not from the
# visitor, so an address in here stands for every visitor at once: it is never
# blocked (by itself or by hand) and never locks logins for everyone. Its
# events are still logged.
JARINGAN_PROXY = [
    ipaddress.ip_network(j.strip(), strict=False)
    for j in __import__("os").environ.get("KEAMANAN_JARINGAN_PROXY", "10.88.0.0/16,10.89.0.0/16").split(",")
    if j.strip()
]


def alamat_bersama(alamat):
    """Whether ``alamat`` is a container network's gateway standing for every
    visitor (JARINGAN_PROXY), rather than one visitor."""
    try:
        ip = ipaddress.ip_address(alamat)
    except ValueError:
        return False
    return any(ip.version == j.version and ip in j for j in JARINGAN_PROXY)

POLA_PEMINDAIAN = re.compile(
    r"(\.env\b|/\.git(/|$)|wp-admin|wp-login|wp-content|xmlrpc\.php|phpmyadmin|\.php\d?\b|/cgi-bin/|"
    r"/etc/passwd|\.\./|%2e%2e|/actuator|/vendor/phpunit|/boaform|/hnap1|\.aspx?\b|/solr/|"
    r"/manager/html|/\.aws/|/\.ssh/|/server-status|/config\.json|\.sql\b|\.bak\b|/shell|/console)",
    re.I,
)
POLA_SQL = re.compile(
    r"(\bunion\b[\s\S]{0,40}\bselect\b|\b(or|and)\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+|'\s*(or|and)\s*'|"
    r"\bsleep\s*\(\s*\d|\bbenchmark\s*\(|information_schema|;\s*(drop|delete|insert|update)\s|--\s*$|/\*.*\*/)",
    re.I,
)
POLA_XSS = re.compile(r"(<\s*script|javascript\s*:|\bon(error|load|mouseover)\s*=|<\s*(img|svg|iframe)\b[^>]*>)", re.I)
POLA_ALAT = re.compile(
    r"(sqlmap|nikto|nmap|masscan|zgrab|acunetix|nuclei|wpscan|dirbuster|gobuster|ffuf|hydra|nessus|openvas|"
    r"w3af|arachni|burpcollaborator|commix|xsstrike)",
    re.I,
)


def _teks_permintaan(request):
    """Path and query string, URL-decoded twice (attacks often encode twice)."""
    mentah = request.get_full_path()
    return unquote_plus(unquote_plus(mentah))


def periksa(request):
    """(jenis, tingkat, detail) when the request looks like an attack, else None."""
    from .models import AktivitasMencurigakan as A

    ua = request.META.get("HTTP_USER_AGENT", "")
    cocok = POLA_ALAT.search(ua)
    if cocok:
        return A.Jenis.ALAT_PERETAS, A.Tingkat.TINGGI, f"User agent: {cocok.group(0)}"
    teks = _teks_permintaan(request)
    for pola, jenis in ((POLA_SQL, A.Jenis.SQL_INJECTION), (POLA_XSS, A.Jenis.XSS), (POLA_PEMINDAIAN, A.Jenis.PEMINDAIAN)):
        cocok = pola.search(teks)
        if cocok:
            return jenis, A.Tingkat.TINGGI, f"Pola: {cocok.group(0)[:120]}"
    return None


def catat(request, jenis, tingkat="sedang", detail="", ip=None):
    """Log one security event; block the address when it keeps attacking."""
    from .models import AktivitasMencurigakan

    user = getattr(request, "user", None)
    alamat = ip or ip_klien(request)
    try:
        ipaddress.ip_address(alamat)
    except ValueError:
        return
    AktivitasMencurigakan.objects.create(
        ip=alamat, jenis=jenis, tingkat=tingkat, metode=request.method[:10],
        path=request.get_full_path()[:500], user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
        user=user if user is not None and user.is_authenticated else None, detail=detail[:300],
    )
    _blokir_bila_berulang(request, alamat)
    _bersihkan_kadang()
    from .realtime import kabarkan
    kabarkan("keamanan")


def _blokir_bila_berulang(request, alamat):
    from django.conf import settings

    from .models import AktivitasMencurigakan, IpBlokir

    # Off unless KEAMANAN_BLOKIR_OTOMATIS is on: behind rootless podman every
    # visitor may come from one address (JARINGAN_PROXY), and no visitor is to
    # be shut out by itself. Attacks are still logged; blocking is by hand.
    if not getattr(settings, "KEAMANAN_BLOKIR_OTOMATIS", False):
        return
    if alamat in TIDAK_DIBLOKIR_OTOMATIS or alamat_bersama(alamat) or diblokir(alamat):
        return
    sejak = timezone.now() - JENDELA_OTOMATIS
    # Failed and locked logins have their own lock (batas_login): not counted here.
    baru = AktivitasMencurigakan.objects.filter(ip=alamat, waktu__gte=sejak).exclude(
        jenis__in=[AktivitasMencurigakan.Jenis.LOGIN_GAGAL, AktivitasMencurigakan.Jenis.LOGIN_TERKUNCI],
    )
    tinggi = baru.filter(tingkat=AktivitasMencurigakan.Tingkat.TINGGI).count()
    semua = baru.count()
    if tinggi < BATAS_TINGGI and semua < BATAS_SEMUA:
        return
    with transaction.atomic():
        _, dibuat = IpBlokir.objects.get_or_create(alamat=alamat, defaults={
            "alasan": f"Otomatis: {tinggi} serangan berat / {semua} kejadian dalam {int(JENDELA_OTOMATIS.total_seconds() // 60)} menit",
            "otomatis": True, "sampai": timezone.now() + BLOKIR_OTOMATIS,
        })
    if dibuat:
        AktivitasMencurigakan.objects.create(
            ip=alamat, jenis=AktivitasMencurigakan.Jenis.IP_DIBLOKIR, tingkat=AktivitasMencurigakan.Tingkat.TINGGI,
            metode=request.method[:10], path=request.get_full_path()[:500],
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300], detail="Diblokir otomatis selama 24 jam",
        )
        segarkan_blokir()


_hitung_simpan = 0


def _bersihkan_kadang():
    """Every 200th event, drop the ones older than SIMPAN_HARI."""
    global _hitung_simpan
    _hitung_simpan += 1
    if _hitung_simpan % 200 == 0:
        from .models import AktivitasMencurigakan
        AktivitasMencurigakan.objects.filter(waktu__lt=timezone.now() - datetime.timedelta(days=SIMPAN_HARI)).delete()


# --- Blacklist, read once per few seconds per process -----------------------

_jaringan = []  # [(network, row id)]
_dimuat = float("-inf")  # never read yet: stale whatever the clock says
_versi_dimuat = -1


def _segar_detik(bawaan):
    """How long the blacklist / maintenance state is trusted before it is read
    again (KEAMANAN_SEGAR_DETIK; long in the test run, where a page's query
    count must not depend on when the last read was)."""
    from django.conf import settings
    return getattr(settings, "KEAMANAN_SEGAR_DETIK", bawaan)


def segarkan_blokir():
    """Re-read the blacklist here at once, and tell the other processes."""
    global _dimuat
    _dimuat = float("-inf")
    from .realtime import kabarkan
    kabarkan("blokir")


def _muat_blokir():
    global _jaringan, _dimuat, _versi_dimuat
    from . import realtime
    from .models import IpBlokir

    versi = realtime.versi("blokir")
    if time.monotonic() - _dimuat < _segar_detik(10) and versi == _versi_dimuat:
        return _jaringan
    sekarang = timezone.now()
    IpBlokir.objects.filter(sampai__lt=sekarang).delete()  # expired blocks go
    hasil = []
    for pk, alamat in IpBlokir.objects.values_list("pk", "alamat"):
        try:
            hasil.append((ipaddress.ip_network(alamat, strict=False), pk))
        except ValueError:
            continue
    _jaringan, _dimuat, _versi_dimuat = hasil, time.monotonic(), versi
    return hasil


def diblokir(alamat):
    try:
        ip = ipaddress.ip_address(alamat)
    except ValueError:
        return False
    return any(ip.version == jaringan.version and ip in jaringan for jaringan, _ in _muat_blokir())


def memuat_alamat_penting(alamat, ip_sendiri):
    """Whether blocking ``alamat`` (an IP or a range) would shut out the
    superuser blocking it, or the server itself."""
    try:
        jaringan = ipaddress.ip_network(alamat, strict=False)
    except ValueError:
        return False
    if any(jaringan.version == j.version and jaringan.overlaps(j) for j in JARINGAN_PROXY):
        return True  # would shut out every visitor (see JARINGAN_PROXY)
    for penting in {ip_sendiri, *TIDAK_DIBLOKIR_OTOMATIS}:
        try:
            ip = ipaddress.ip_address(penting)
        except ValueError:
            continue
        if ip.version == jaringan.version and ip in jaringan:
            return True
    return False


def alamat_sah(teks):
    """``teks`` as a normalized IP or CIDR, or None."""
    try:
        return str(ipaddress.ip_network(teks.strip(), strict=False)) if "/" in teks else str(ipaddress.ip_address(teks.strip()))
    except ValueError:
        return None


async def tolak_bila_diblokir(ip):
    """For the Bolt API routes, which don't pass Django's middleware: 403 when
    the client is on the blacklist. ``ip``: the route's X-Real-IP header (set by
    nginx), declared as a parameter, e.g. ``x_real_ip: str | None =
    Header(None, alias="x-real-ip")``; Bolt hands a route only the headers it
    declares, so request.headers would be empty."""
    from asgiref.sync import sync_to_async
    from django_bolt.exceptions import HTTPException

    if ip and await sync_to_async(diblokir)(ip):
        raise HTTPException(status_code=403, detail="Forbidden")


class KeamananMiddleware:
    """First in line: a blacklisted address gets 403 and nothing else runs;
    a request that looks like an attack is logged (and answered as usual)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        alamat = ip_klien(request)
        if diblokir(alamat):
            return HttpResponse(render_to_string("keamanan/diblokir.html"), status=403)
        temuan = periksa(request)
        if temuan:
            catat(request, *temuan)
        return self.get_response(request)


def csrf_gagal(request, reason=""):
    """CSRF_FAILURE_VIEW: logged as an event, then Django's usual 403 page."""
    from django.views.csrf import csrf_failure

    from .models import AktivitasMencurigakan
    catat(request, AktivitasMencurigakan.Jenis.CSRF, AktivitasMencurigakan.Tingkat.SEDANG, reason)
    return csrf_failure(request, reason=reason)


# --- Maintenance -------------------------------------------------------------

_pemeliharaan = (float("-inf"), -1, None)  # (read at, realtime version then, row or None)


def pemeliharaan():
    """The maintenance row while maintenance is on, else None. Read again
    every 5 s, or at once when a notice says it changed."""
    global _pemeliharaan
    from . import realtime
    from .models import Pemeliharaan

    dibaca, versi, baris = _pemeliharaan
    sekarang_versi = realtime.versi("pemeliharaan")
    if time.monotonic() - dibaca >= _segar_detik(5) or versi != sekarang_versi:
        baris = Pemeliharaan.objects.first()
        _pemeliharaan = (time.monotonic(), sekarang_versi, baris)
    return baris if baris is not None and baris.aktif else None


def lupakan_pemeliharaan():
    global _pemeliharaan
    _pemeliharaan = (float("-inf"), -1, None)
    from .realtime import kabarkan
    kabarkan("pemeliharaan")


# Still reachable during maintenance: signing in (a superuser must get in),
# the files every page needs, and the live stream.
_TERBUKA = ("/login/", "/logout/", "/static/", "/sse/", "/manifest.webmanifest", "/sw.js")


class PemeliharaanMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        baris = pemeliharaan()
        if baris is not None and not request.path.startswith(_TERBUKA) and not getattr(request.user, "is_superuser", False):
            response = HttpResponse(render_to_string("keamanan/pemeliharaan.html", {"pemeliharaan": baris}, request=request), status=503)
            response["Retry-After"] = "600"
            return response
        return self.get_response(request)
