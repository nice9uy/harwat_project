"""Login throttling for the web login page.

After BATAS_USERNAME failed attempts on one username, or BATAS_IP from one
client IP, within JENDELA, that username or IP is refused for KUNCI. A
successful login clears the username's count.
"""
import datetime

from django.db import transaction
from django.utils import timezone

from .models import GagalLogin

BATAS_USERNAME = 5
BATAS_IP = 30
JENDELA = datetime.timedelta(minutes=15)
KUNCI = datetime.timedelta(minutes=15)


def ip_klien(request):
    """The client's address: nginx's X-Real-IP (it sets the header itself,
    overwriting whatever the client sent), else the socket peer."""
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR", "")


def _kunci(request, username):
    daftar = [f"ip:{ip_klien(request)}"]
    if username:
        daftar.append(f"u:{username.strip().lower()[:150]}")
    return daftar


def menit_terkunci(request, username):
    """Minutes left on a lock for this username or IP, or 0."""
    sekarang = timezone.now()
    sampai = (
        GagalLogin.objects.filter(kunci__in=_kunci(request, username), terkunci_sampai__gt=sekarang)
        .order_by("-terkunci_sampai").values_list("terkunci_sampai", flat=True).first()
    )
    if sampai is None:
        return 0
    return max(1, -(-int((sampai - sekarang).total_seconds()) // 60))


def catat_gagal(request, username):
    sekarang = timezone.now()
    with transaction.atomic():
        for kunci in _kunci(request, username):
            baris, _ = GagalLogin.objects.select_for_update().get_or_create(
                kunci=kunci, defaults={"sejak": sekarang},
            )
            if sekarang - baris.sejak > JENDELA:
                baris.jumlah, baris.sejak, baris.terkunci_sampai = 0, sekarang, None
            baris.jumlah += 1
            batas = BATAS_IP if kunci.startswith("ip:") else BATAS_USERNAME
            terkunci = baris.jumlah >= batas
            if terkunci:
                baris.terkunci_sampai = sekarang + KUNCI
            baris.save()
    # Hacking Activity: every failure, and a lock as a heavier one.
    from .keamanan import catat
    from .models import AktivitasMencurigakan as A
    catat(request, A.Jenis.LOGIN_GAGAL, A.Tingkat.RENDAH, f"Nama pengguna: {username[:100]}")
    if terkunci:
        catat(request, A.Jenis.LOGIN_TERKUNCI, A.Tingkat.TINGGI, f"Dikunci {int(KUNCI.total_seconds() // 60)} menit: {username[:100]}")


def catat_berhasil(username):
    GagalLogin.objects.filter(kunci=f"u:{username.strip().lower()[:150]}").delete()


# The public Daftar Ketua Tim form says whether a username is taken, so it is
# throttled per client IP too: BATAS_DAFTAR sends within JENDELA, then KUNCI.
BATAS_DAFTAR = 20


def _kunci_daftar(request):
    return f"daftar-ip:{ip_klien(request)}"


def menit_terkunci_daftar(request):
    """Minutes left before this IP may send the Daftar form again, or 0."""
    sekarang = timezone.now()
    sampai = (
        GagalLogin.objects.filter(kunci=_kunci_daftar(request), terkunci_sampai__gt=sekarang)
        .values_list("terkunci_sampai", flat=True).first()
    )
    if sampai is None:
        return 0
    return max(1, -(-int((sampai - sekarang).total_seconds()) // 60))


def catat_daftar(request):
    """Count one send of the Daftar form from this IP."""
    sekarang = timezone.now()
    with transaction.atomic():
        baris, _ = GagalLogin.objects.select_for_update().get_or_create(
            kunci=_kunci_daftar(request), defaults={"sejak": sekarang},
        )
        if sekarang - baris.sejak > JENDELA:
            baris.jumlah, baris.sejak, baris.terkunci_sampai = 0, sekarang, None
        baris.jumlah += 1
        if baris.jumlah >= BATAS_DAFTAR:
            if not baris.terkunci_sampai:
                from .keamanan import catat
                from .models import AktivitasMencurigakan as A
                catat(request, A.Jenis.DAFTAR_SPAM, A.Tingkat.SEDANG, f"{baris.jumlah} kali kirim form Daftar dalam 15 menit")
            baris.terkunci_sampai = sekarang + KUNCI
        baris.save()
