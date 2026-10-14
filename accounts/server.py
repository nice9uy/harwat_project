"""Server menu (superuser only): the Podman containers that are running and
the machine's CPU, RAM and storage, refreshed every few seconds."""
import calendar
import datetime
import http.client
import json
import os
import shutil
import socket
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

# Seconds between refreshes of the page's content.
JEDA_DETIK = 1


class _UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP over a unix socket (the Podman API)."""

    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def _sambungan():
    """A connection to the Podman API: the read-only relay at
    settings.PODMAN_API (production: http://podman-api:2375, which passes on
    the two lookups below and refuses anything else), else the socket at
    settings.PODMAN_SOCKET itself (development)."""
    from urllib.parse import urlsplit

    if settings.PODMAN_API:
        alamat = urlsplit(settings.PODMAN_API)
        return http.client.HTTPConnection(alamat.hostname, alamat.port or 80, timeout=3)
    return _UnixHTTPConnection(settings.PODMAN_SOCKET, timeout=3)


def _nama_image(image):
    """Image name without its registry path, a sha256 digest cut to 12 characters."""
    nama = image.rsplit("/", 1)[-1]
    if "@sha256:" in nama:
        nama, digest = nama.split("@sha256:", 1)
        nama = f"{nama}@{digest[:12]}"
    return nama


# {container name: (CPU ns used, clock ns)} of the previous look, for the CPU
# share since then (the API's own figure is the average since the start).
_aktivitas_terakhir = {}


def _aktivitas():
    """{container name: {"cpu": percent of one core, "ram": bytes, "pid": n}}
    for the running containers; empty when Podman gives no figures."""
    global _aktivitas_terakhir
    try:
        conn = _sambungan()
        conn.request("GET", "/v4.0.0/libpod/containers/stats?stream=false")
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
    except (OSError, ValueError, http.client.HTTPException):
        return {}
    if not isinstance(data, dict):
        return {}
    hasil, kini = {}, {}
    for st in data.get("Stats") or []:
        nama = st.get("Name") or ""
        sampel = (st.get("CPUNano") or 0, st.get("SystemNano") or 0)
        kini[nama] = sampel
        lalu = _aktivitas_terakhir.get(nama)
        if lalu and sampel[1] > lalu[1] and sampel[0] >= lalu[0]:
            cpu_persen = 100 * (sampel[0] - lalu[0]) / (sampel[1] - lalu[1])
        else:
            cpu_persen = st.get("CPU") or 0.0
        hasil[nama] = {"cpu": round(cpu_persen, 1), "ram": st.get("MemUsage") or 0, "pid": st.get("PIDs") or 0}
    _aktivitas_terakhir = kini
    return hasil


def kontainer():
    """(containers, error): every Podman container, running ones first then
    by name, from the Podman API (see _sambungan)."""
    path = settings.PODMAN_SOCKET
    if not settings.PODMAN_API and not os.path.exists(path):
        return [], f"Socket Podman tidak ditemukan di {path}."
    try:
        conn = _sambungan()
        conn.request("GET", "/v4.0.0/libpod/containers/json?all=true")
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
    except (OSError, ValueError, http.client.HTTPException) as err:
        return [], f"Podman tidak bisa dihubungi: {err}"
    aktivitas = _aktivitas()
    hasil = []
    for c in data:
        mulai = c.get("StartedAt") or 0
        hasil.append({
            "nama": ", ".join(c.get("Names") or []),
            "aktivitas": aktivitas.get((c.get("Names") or [""])[0]),
            "image": _nama_image(c.get("Image") or ""),
            "hidup": c.get("State") == "running",
            "state": c.get("State") or "-",
            "sejak": timezone.datetime.fromtimestamp(mulai, tz=timezone.get_current_timezone()) if mulai > 0 else None,
            "port": ", ".join(sorted({
                f"{p.get('host_port')}→{p.get('container_port')}" for p in c.get("Ports") or [] if p.get("host_port")
            })),
        })
    hasil.sort(key=lambda k: (not k["hidup"], k["nama"]))
    return hasil, ""


def _cpu_sample():
    """(busy, total) jiffies summed over all CPUs, from /proc/stat."""
    with open("/proc/stat") as f:
        angka = [int(x) for x in f.readline().split()[1:]]
    idle = angka[3] + (angka[4] if len(angka) > 4 else 0)  # idle + iowait
    return sum(angka) - idle, sum(angka)


_cpu_terakhir = None


def cpu():
    """CPU use in percent since the previous call in this process (the page
    polls, so that is the last few seconds); the first call measures 0.2 s."""
    global _cpu_terakhir
    try:
        sekarang = _cpu_sample()
        if _cpu_terakhir is None or sekarang[1] == _cpu_terakhir[1]:
            _cpu_terakhir = sekarang
            time.sleep(0.2)
            sekarang = _cpu_sample()
        sibuk, total = sekarang[0] - _cpu_terakhir[0], sekarang[1] - _cpu_terakhir[1]
        _cpu_terakhir = sekarang
        persen = round(100 * sibuk / total, 1) if total > 0 else 0.0
    except (OSError, ValueError, IndexError):
        return None
    return {"persen": max(0.0, min(100.0, persen)), "inti": os.cpu_count() or 1, "beban": os.getloadavg()}


def ram():
    """Memory in bytes from /proc/meminfo: total, used (total - available)."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for baris in f:
                kunci, nilai = baris.split(":", 1)
                info[kunci] = int(nilai.split()[0]) * 1024
        total, tersedia = info["MemTotal"], info["MemAvailable"]
    except (OSError, ValueError, KeyError):
        return None
    return {
        "total": total, "terpakai": total - tersedia,
        "persen": round(100 * (total - tersedia) / total, 1) if total else 0.0,
        "swap_total": info.get("SwapTotal", 0),
        "swap_terpakai": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
    }


def storage():
    """Disk use of the app's filesystems: the system root and, when it is on
    another filesystem, where uploads are kept."""
    hasil, dilihat = [], set()
    for label, path in (("Sistem", "/"), ("Media (foto)", str(settings.MEDIA_ROOT))):
        try:
            perangkat = os.stat(path).st_dev
            pakai = shutil.disk_usage(path)
        except OSError:
            continue
        if perangkat in dilihat:
            continue
        dilihat.add(perangkat)
        hasil.append({
            "label": label, "path": path, "total": pakai.total, "terpakai": pakai.used,
            "persen": round(100 * pakai.used / pakai.total, 1) if pakai.total else 0.0,
        })
    return hasil


def _tambah_bulan(waktu, n):
    """``waktu`` n months on; a day the target month lacks becomes its last."""
    tahun, bulan = divmod(waktu.year * 12 + waktu.month - 1 + n, 12)
    return waktu.replace(year=tahun, month=bulan + 1, day=min(waktu.day, calendar.monthrange(tahun, bulan + 1)[1]))


def lama_hidup(sejak, kini):
    """Calendar distance between two datetimes as whole years, months and
    days (plus the hours left over), the way a person would count it."""
    bulan = (kini.year - sejak.year) * 12 + kini.month - sejak.month
    if _tambah_bulan(sejak, bulan) > kini:
        bulan -= 1
    sisa = kini - _tambah_bulan(sejak, bulan)
    return {"tahun": bulan // 12, "bulan": bulan % 12, "hari": sisa.days, "jam": sisa.seconds // 3600}


def hidup():
    """How long the machine has been up (/proc/uptime), or None off Linux."""
    try:
        with open("/proc/uptime") as f:
            detik = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    kini = timezone.localtime()
    sejak = kini - datetime.timedelta(seconds=detik)
    return {"sejak": sejak, **lama_hidup(sejak, kini)}


def _konteks():
    daftar, galat = kontainer()
    return {
        "kontainer": daftar,
        "kontainer_galat": galat,
        "jumlah_hidup": sum(1 for k in daftar if k["hidup"]),
        "cpu": cpu(),
        "ram": ram(),
        "storage": storage(),
        "hidup": hidup(),
        "waktu": timezone.localtime(),
        "jeda": JEDA_DETIK,
    }


@login_required
def server_view(request):
    if not request.user.is_superuser:
        raise Http404
    return render(request, "accounts/server.html", _konteks())


@login_required
def server_partial(request):
    """The page's content alone, fetched every JEDA_DETIK seconds."""
    if not request.user.is_superuser:
        raise Http404
    return render(request, "accounts/_server_content.html", _konteks())
