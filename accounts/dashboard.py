"""Dashboard data: fleet counts, schedule and a feed of the latest activities.

Every function takes ``users``: the user pks whose work the viewer may see
(see cakupan()), or None for everything.
"""
import contextlib
import contextvars
import functools
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.utils import timezone

from fleet.models import Jadwal, Servis, Vehicle

from . import golongan

# Every vehicle group is Kendaraan, Golongan "B" included. Non Kendaraan has
# no group of its own yet (its Form Tambah tab isn't available either).
KENDARAAN_KODE = list(Vehicle.GroupKendaraan.values)
NON_KENDARAAN_KODE = []


# One page asks the same thing several times over (the vehicles due a
# service, a group's summary, a matra's users): inside sekali() each answer
# is worked out once and reused. Outside it nothing is remembered.
_INGATAN = contextvars.ContextVar("dashboard_ingatan", default=None)


@contextlib.contextmanager
def sekali():
    """For the length of one request: the functions marked @_ingat answer a
    repeated question from memory."""
    token = _INGATAN.set({})
    try:
        yield
    finally:
        _INGATAN.reset(token)


def _kunci(nilai):
    """A hashable stand-in for an argument: sets and lists by content, a
    user by pk, anything unhashable (a golongan config) by identity."""
    if nilai is None or isinstance(nilai, (str, int, bool)):
        return nilai
    if isinstance(nilai, (set, frozenset)):
        return frozenset(nilai)
    if isinstance(nilai, (list, tuple)):
        return tuple(_kunci(n) for n in nilai)
    if hasattr(nilai, "pk"):
        return (type(nilai).__name__, nilai.pk)
    return id(nilai)


def _ingat(fungsi):
    @functools.wraps(fungsi)
    def pembungkus(*args):
        ingatan = _INGATAN.get()
        if ingatan is None:
            return fungsi(*args)
        kunci = (fungsi.__name__, *(_kunci(a) for a in args))
        if kunci not in ingatan:
            ingatan[kunci] = fungsi(*args)
        return ingatan[kunci]
    return pembungkus


@_ingat
def cakupan(user):
    """User pks whose work ``user`` sees on the dashboard: themselves and
    everyone under them (Admin > Ketua Tim > Tim; a Pimpinan Tim's are the
    Ketua Tim they picked), so another Admin's teams stay out. None, meaning
    everything, for a superuser, Pimpinan and users outside that tree."""
    from . import roles
    from .models import Anggota

    kode = roles.keanggotaan_kode(user)
    if kode not in (roles.ADMIN_ROLE, roles.KETUA_TIM, roles.PIMPINAN_TIM):
        return None
    users = {user.pk}
    if kode == roles.KETUA_TIM:
        ketua = Anggota.objects.filter(user=user, depth=1)
    elif kode == roles.PIMPINAN_TIM:
        ketua = Anggota.objects.filter(pimpinan_tim__pimpinan=user, depth=1)
    else:
        ketua = Anggota.objects.filter(admin=user, depth=1)
    for node in ketua:
        users.add(node.user_id)
        users.update(node.get_children().values_list("user_id", flat=True))
    return users


@_ingat
def pengguna_matra(matra):
    """User pks of one matra: the users with it, plus the Ketua Tim and Tim
    members made before a matra was asked of them, who follow the one above
    them (their Admin's, their Ketua Tim's)."""
    from django.contrib.auth.models import User
    from .models import Anggota

    users = set(User.objects.filter(publik__matra=matra).values_list("pk", flat=True))
    ikut = {}  # root path -> the team's matra, for members without their own
    nodes = list(Anggota.objects.select_related("user__publik", "admin__publik").order_by("depth"))
    for node in nodes:
        sendiri = getattr(getattr(node.user, "publik", None), "matra", "")
        if node.depth == 1:
            ikut[node.path] = sendiri or getattr(getattr(node.admin, "publik", None), "matra", "")
        if not sendiri and ikut.get(node.path[:Anggota.steplen]) == matra:
            users.add(node.user_id)
    return users


@_ingat
def cakupan_matra(user, matra):
    """cakupan() narrowed to one matra's users ("" for no narrowing)."""
    users = cakupan(user)
    if not matra:
        return users
    semua = pengguna_matra(matra)
    return semua if users is None else users & semua


def _milik(qs, field, users):
    """``qs`` narrowed to rows whose ``field`` (a user) is in ``users``."""
    return qs if users is None else qs.filter(**{f"{field}__in": users})


def _kendaraan(users):
    """Vehicles in scope: those added by one of ``users``."""
    return _milik(Vehicle.objects.all(), "ditambahkan_oleh", users)


# Rows on the dashboard's Sedang Dikerjakan card.
SEDANG_MAKS = 10


@_ingat
def _perlu_servis(kodes, users):
    """{vehicle pk: reason} of the vehicles in scope that are due a service (km_jadwal.perlu_servis)."""
    from .km_jadwal import perlu_servis

    if not kodes:  # Non Kendaraan has no groups yet: nothing to look up
        return {}
    return perlu_servis(_kendaraan(users).filter(group_kendaraan__in=kodes))


@_ingat
def _fleet_summary_group(kodes, users):
    if not kodes:
        return {"service": 0, "total": 0, "ready": 0, "in_repair": 0, "due_soon": 0, "repaired": 0}
    status_counts = dict(
        _kendaraan(users).filter(group_kendaraan__in=kodes).values_list("status").annotate(count=Count("id"))
    )
    return {
        # Not a status: a vehicle can be due a service whatever its condition.
        "service": len(_perlu_servis(kodes, users)),
        "total": sum(status_counts.values()),
        "ready": status_counts.get(Vehicle.Status.SIAP_PAKAI, 0),
        "in_repair": status_counts.get(Vehicle.Status.DALAM_PERBAIKAN, 0),
        "due_soon": status_counts.get(Vehicle.Status.PERLU_SERVIS, 0),
        "repaired": status_counts.get(Vehicle.Status.SUDAH_DIPERBAIKI, 0),
    }

# The summary cards open a table of their vehicles: card -> (title, statuses or None for all).
KARTU_KENDARAAN = {
    "total": ("Semua", None),
    "siap": ("Siap", [Vehicle.Status.SIAP_PAKAI]),
    "rusak_ringan": ("Rusak Ringan", [Vehicle.Status.PERLU_SERVIS]),
    "rusak_berat": ("Rusak Berat", [Vehicle.Status.DALAM_PERBAIKAN]),
    "sudah_diperbaiki": ("Sudah Diperbaiki", [Vehicle.Status.SUDAH_DIPERBAIKI]),
    # Any status: picked by km_jadwal.perlu_servis instead.
    "perlu_servis": ("Perlu Servis", None),
}


def kendaraan_kartu(kartu, non_kendaraan, users, cari=""):
    """(title, vehicles, reasons) behind one summary card, in the viewer's
    scope; ``cari`` narrows them by No. Registrasi, Merk/Type, No. Chasis or
    No. Mesin. ``reasons``: {vehicle pk: why it is due}, for Perlu Servis only."""
    judul, status = KARTU_KENDARAAN[kartu]
    kodes = NON_KENDARAAN_KODE if non_kendaraan else KENDARAAN_KODE
    qs = _kendaraan(users).filter(group_kendaraan__in=kodes)
    if status is not None:
        qs = qs.filter(status__in=status)
    alasan = {}
    if kartu == "perlu_servis":
        alasan = _perlu_servis(kodes, users)
        qs = qs.filter(pk__in=list(alasan))
    if cari:
        qs = qs.filter(
            Q(nopol__icontains=cari) | Q(merek__icontains=cari)
            | Q(no_chasis__icontains=cari) | Q(no_mesin__icontains=cari)
        )
    jenis = "Non Kendaraan" if non_kendaraan else "Kendaraan"
    return f"{jenis} {judul}", qs.select_related("penambah__satuan").order_by("nopol", "id"), alasan


# The card modal's pie chart: this many units as slices, the rest summed up
# in one more (so the slices stay tellable apart by colour).
SATUAN_MAKS = 7
TANPA_SATUAN = "Tanpa satuan"
PIE_R, PIE_PUSAT = 92, 100


def satuan_pie(qs):
    """Pie chart of the vehicles in ``qs`` per Satuan (the unit of whoever
    added them, from that biodata): the SATUAN_MAKS biggest, then "Lainnya".
    Each slice carries the unit's uuid for the modal's filter ("-" for
    vehicles without one, "" for Lainnya, which isn't a filter), its colour
    slot (1-8, 8 being Lainnya's grey) and its SVG path ("" for a slice that
    is the whole pie, drawn as a circle)."""
    import math

    baris = [
        (nama or TANPA_SATUAN, str(uid) if uid else "-", n)
        for nama, uid, n in qs.order_by().values_list("penambah__satuan__nama", "penambah__satuan__uuid")
        .annotate(n=Count("id")).order_by("-n", "penambah__satuan__nama")
    ]
    if len(baris) > SATUAN_MAKS:
        sisa = baris[SATUAN_MAKS:]
        baris = baris[:SATUAN_MAKS] + [(f"Lainnya ({len(sisa)} satuan)", "", sum(n for _, _, n in sisa))]
    total = sum(n for _, _, n in baris)
    irisan, sudut = [], -math.pi / 2  # from 12 o'clock, clockwise
    for i, (label, uid, n) in enumerate(baris):
        lebar = 2 * math.pi * n / total
        x1, y1 = PIE_PUSAT + PIE_R * math.cos(sudut), PIE_PUSAT + PIE_R * math.sin(sudut)
        sudut += lebar
        x2, y2 = PIE_PUSAT + PIE_R * math.cos(sudut), PIE_PUSAT + PIE_R * math.sin(sudut)
        irisan.append({
            "nama": label, "uuid": uid, "nilai": n, "persen": round(100 * n / total, 1),
            "warna": 8 if not uid else i + 1,
            "path": "" if n == total else (
                f"M{PIE_PUSAT},{PIE_PUSAT} L{x1:.2f},{y1:.2f} "
                f"A{PIE_R},{PIE_R} 0 {1 if lebar > math.pi else 0} 1 {x2:.2f},{y2:.2f} Z"
            ),
        })
    return {"irisan": irisan, "total": total, "r": PIE_R, "pusat": PIE_PUSAT, "sisi": 2 * PIE_PUSAT}


def _irisan_pie(bagian):
    """Pie slices for [(label, n, css class)], clockwise from 12 o'clock:
    each with its share and SVG path ("" for a slice that is the whole pie,
    drawn as a circle). Parts of 0 are left out."""
    import math

    bagian = [b for b in bagian if b[1]]
    total = sum(n for _, n, _ in bagian)
    irisan, sudut = [], -math.pi / 2
    for label, n, kelas in bagian:
        lebar = 2 * math.pi * n / total
        x1, y1 = PIE_PUSAT + PIE_R * math.cos(sudut), PIE_PUSAT + PIE_R * math.sin(sudut)
        sudut += lebar
        x2, y2 = PIE_PUSAT + PIE_R * math.cos(sudut), PIE_PUSAT + PIE_R * math.sin(sudut)
        irisan.append({
            "label": label, "nilai": n, "persen": round(100 * n / total, 1), "kelas": kelas,
            "path": "" if n == total else (
                f"M{PIE_PUSAT},{PIE_PUSAT} L{x1:.2f},{y1:.2f} "
                f"A{PIE_R},{PIE_R} 0 {1 if lebar > math.pi else 0} 1 {x2:.2f},{y2:.2f} Z"
            ),
        })
    return irisan


def ringkasan_matra(user, kodes):
    """The dashboard's Semua Matra view: a pie per matra of its vehicles'
    condition (Siap, Rusak Ringan, Rusak Berat), and a row of detail per matra (its vehicles by condition and those due
    a service). A last "Tanpa matra" row holds the vehicles of users without
    one, when there are any."""
    from . import roles

    kolom = {
        Vehicle.Status.SIAP_PAKAI: "siap", Vehicle.Status.PERLU_SERVIS: "ringan",
        Vehicle.Status.DALAM_PERBAIKAN: "berat", Vehicle.Status.SUDAH_DIPERBAIKI: "diperbaiki",
    }

    def kosong():
        return {"total": 0, "siap": 0, "ringan": 0, "berat": 0, "diperbaiki": 0, "servis": 0}

    # One pass over the vehicles in scope: each is counted for the whole and
    # for the matra of whoever added it (what is due a service worked out once).
    lingkup = cakupan(user)
    servis = _perlu_servis(kodes, lingkup)
    per_matra = [(kode, label, cakupan_matra(user, kode), kosong()) for kode, label in roles.MATRA]
    semua = kosong()
    kendaraan = _kendaraan(lingkup).filter(group_kendaraan__in=kodes).values_list("pk", "status", "ditambahkan_oleh_id")
    for pk, status, penambah in kendaraan.iterator():
        sasaran = [semua] + [r for _, _, anggota, r in per_matra if penambah in anggota]
        for r in sasaran:
            r["total"] += 1
            if status in kolom:
                r[kolom[status]] += 1
            if pk in servis:
                r["servis"] += 1
    sisa = dict(semua)
    baris = []
    for i, (kode, label, _, r) in enumerate(per_matra, start=1):
        for kunci in sisa:
            sisa[kunci] -= r[kunci]
        baris.append({"kode": kode, "label": label, "warna": i, **r})
    if sisa["total"] > 0:
        baris.append({"kode": "", "label": "Tanpa matra", "warna": 8, **sisa})
    for b in baris:
        # The matra's own pie: its vehicles that are Siap, Rusak Ringan or Rusak Berat.
        kondisi = [("Siap", b["siap"], "pie-siap"), ("Rusak Ringan", b["ringan"], "pie-ringan"), ("Rusak Berat", b["berat"], "pie-berat")]
        b["irisan"] = _irisan_pie(kondisi)
        persen = {i["label"]: i["persen"] for i in b["irisan"]}
        b["legenda"] = [{"label": l, "nilai": n, "kelas": k, "persen": persen.get(l, 0)} for l, n, k in kondisi]
    return {
        "baris": baris, "total": semua,
        "r": PIE_R, "pusat": PIE_PUSAT, "sisi": 2 * PIE_PUSAT,
    }


def saring_satuan(qs, nilai):
    """``qs`` narrowed to one unit's vehicles: ``nilai`` is a Satuan uuid, or
    "-" for the vehicles without a unit. Returns (queryset, the unit's name
    or "" when not filtered)."""
    from .models import Satuan

    if nilai == "-":
        return qs.filter(penambah__satuan=None), TANPA_SATUAN
    try:
        satuan = Satuan.objects.filter(uuid=nilai).first() if nilai else None
    except (ValueError, ValidationError):
        satuan = None
    if satuan is None:
        return qs, ""
    return qs.filter(penambah__satuan=satuan), satuan.nama


# Rows on the dashboard's Rusak/Tidak Bisa Diperbaiki tab.
RUSAK_MAKS = 200


def rusak_berat(users, batas=RUSAK_MAKS):
    """The Rusak/Tidak Bisa Diperbaiki tab: the vehicles in scope that are
    Rusak Berat, newest first: declared so with Form Rusak/Tidak Layak Pakai
    (``v.dinyatakan``: the latest declaration) or by their last inspection
    concluding Tidak Layak Pakai (``v.periksa``, with how many of its parts
    are Rusak Berat). Returns (rows, total); ``batas``: how many rows at most
    (None for all, as the PDF lists them)."""
    qs = _kendaraan(users).filter(status=Vehicle.Status.DALAM_PERBAIKAN).select_related("penambah__satuan")
    total = qs.count()
    vehicles = {v.pk: v for v in qs}
    from .models import KendaraanRusak

    for v in vehicles.values():
        v.periksa = v.dinyatakan = None
    for d in KendaraanRusak.objects.filter(vehicle__in=list(vehicles)).select_related("pelapor").order_by("dibuat_pada", "id"):
        vehicles[d.vehicle_id].dinyatakan = d  # ends on the newest
    for cfg in golongan.GOLONGAN.values():
        terakhir = (
            cfg.pemeriksaan_model.objects.filter(vehicle__in=list(vehicles))
            .select_related("pemeriksa").annotate(jumlah_rb=Count("items", filter=Q(items__kondisi="RB")))
            .order_by("vehicle", "-dibuat_pada", "-id")
        )
        for hasil in terakhir:
            v = vehicles[hasil.vehicle_id]
            if v.periksa is None or hasil.dibuat_pada > v.periksa.dibuat_pada:
                v.periksa = hasil
    for v in vehicles.values():
        waktu = [x.dibuat_pada for x in (v.periksa, v.dinyatakan) if x is not None]
        v.waktu_rusak = max(waktu) if waktu else None
    baris = sorted(
        vehicles.values(), key=lambda v: (v.waktu_rusak.timestamp() if v.waktu_rusak else 0, v.pk), reverse=True,
    )
    return baris[:batas], total


def sparepart_rusak(users, batas=RUSAK_MAKS):
    """The Sparepart half of the Rusak/Tidak Bisa Diperbaiki tab: the parts
    that are Rusak Berat now (komponen_rusak). Returns (rows, total);
    ``batas``: how many rows at most (None for all, as Laporan Rusak lists them)."""
    return komponen_rusak(users, ("RB",), batas=batas)


def komponen_rusak(users, kondisi=("RR", "RB"), kodes=None, batas=None):
    """The parts that are damaged now, on the vehicles in scope: marked with
    one of ``kondisi`` (RR: Rusak Ringan, RB: Rusak Berat) in the vehicle's
    last inspection and not repaired since, or left so by their last repair.
    Each row carries that ``kondisi``. ``kodes``: only these vehicle groups.
    Newest first. Returns (rows, total); ``batas``: how many rows at most."""
    baris = []
    for kode, cfg in golongan.GOLONGAN.items():
        if kodes is not None and kode not in kodes:
            continue
        kendaraan = {
            v.pk: v for v in _kendaraan(users).filter(group_kendaraan=kode).select_related("penambah__satuan")
        }
        if not kendaraan:
            continue
        terakhir = {}  # vehicle id -> its newest inspection
        for hasil in (
            cfg.pemeriksaan_model.objects.filter(vehicle__in=list(kendaraan))
            .select_related("pemeriksa").order_by("dibuat_pada", "id")
        ):
            terakhir[hasil.vehicle_id] = hasil
        periksa = {h.pk: h for h in terakhir.values()}
        # Only a part that was not Baik can be damaged now.
        items = cfg.item_model.objects.filter(pemeriksaan__in=list(periksa)).exclude(kondisi__in=cfg.baik)
        perbaikan = {}  # item id -> its newest repair
        for p in (
            cfg.perbaikan_model.objects.filter(item__pemeriksaan__in=list(periksa))
            .select_related("teknisi").order_by("dibuat_pada", "id")
        ):
            perbaikan[p.item_id] = p
        for item in items:
            diperbaiki = perbaikan.get(item.pk)
            kini = diperbaiki.kondisi if diperbaiki else item.kondisi
            if kini not in kondisi:
                continue
            hasil = periksa[item.pemeriksaan_id]
            baris.append({
                "vehicle": kendaraan[hasil.vehicle_id], "item": item, "periksa": hasil, "perbaikan": diperbaiki,
                "kondisi": kini,
                "waktu": diperbaiki.dibuat_pada if diperbaiki else hasil.dibuat_pada,
                "keterangan": (diperbaiki.keterangan if diperbaiki else item.keterangan),
            })
    baris.sort(key=lambda b: (b["waktu"], b["item"].pk), reverse=True)
    return baris[:batas], len(baris)


def pemeriksaan_terakhir(vehicles):
    """{vehicle pk: time of its newest inspection}, over every group's form."""
    pks = [v.pk for v in vehicles]
    hasil = {}
    for cfg in golongan.GOLONGAN.values():
        for baris in (
            cfg.pemeriksaan_model.objects.filter(vehicle__in=pks).order_by()
            .values("vehicle").annotate(waktu=Max("dibuat_pada"))
        ):
            hasil[baris["vehicle"]] = max(baris["waktu"], hasil.get(baris["vehicle"], baris["waktu"]))
    return hasil


# Kegiatan Terbaru: the newest KEGIATAN_MAKS activities, KEGIATAN_PER_HALAMAN a page.
KEGIATAN_MAKS = 100
KEGIATAN_PER_HALAMAN = 10


def _kegiatan_terbaru(users):
    """Latest inspections, repairs, vehicles added, services and schedules, newest first.

    Each source is one query (limited to KEGIATAN_MAKS), so the feed's cost
    doesn't grow with the data.
    """
    feed = []
    for kode, cfg in golongan.GOLONGAN.items():
        label = Vehicle.GroupKendaraan(kode).label
        inspeksi = (
            _milik(cfg.pemeriksaan_model.objects.all(), "pemeriksa__akun", users)
            .select_related("vehicle", "pemeriksa")
            .annotate(perlu=Count("items", filter=~Q(items__kondisi__in=cfg.baik)))
            .order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]
        )
        for h in inspeksi:
            feed.append({
                "waktu": h.dibuat_pada, "jenis": "pemeriksaan", "oleh": h.pemeriksa.nama,
                "teks": f"memeriksa {h.vehicle.nopol} ({label})",
                "detail": f"{h.perlu} item perlu perbaikan" if h.perlu else "Semua item baik",
            })
        perbaikan = (
            _milik(cfg.perbaikan_model.objects.all(), "teknisi__akun", users)
            .select_related("teknisi", "item__pemeriksaan__vehicle").order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]
        )
        for p in perbaikan:
            feed.append({
                "waktu": p.dibuat_pada, "jenis": "perbaikan", "oleh": p.teknisi.nama,
                "teks": f"memperbaiki {p.item.nama_alat} pada {p.item.pemeriksaan.vehicle.nopol}",
                "detail": f"Kondisi sekarang: {p.get_kondisi_display()}",
            })
    for v in _kendaraan(users).exclude(dibuat_pada=None).order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": v.dibuat_pada, "jenis": "kendaraan", "oleh": "",
            "teks": f"Kendaraan {v.nopol} ({v.merek}) ditambahkan",
            "detail": v.get_group_kendaraan_display(),
        })
    servis = _milik(Servis.objects.all(), "vehicle__ditambahkan_oleh", users)
    for s in servis.select_related("vehicle").order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": s.dibuat_pada, "jenis": "servis", "oleh": "",
            "teks": f"Servis {s.jenis_servis} untuk {s.vehicle.nopol} dicatat",
            "detail": s.bengkel or "",
        })
    jadwal = _milik(Jadwal.objects.all(), "vehicle__ditambahkan_oleh", users)
    for j in jadwal.select_related("vehicle").order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": j.dibuat_pada, "jenis": "jadwal", "oleh": "",
            "teks": f"Jadwal {j.get_kegiatan_display().lower()} {j.vehicle.nopol} dibuat",
            "detail": f"Untuk {j.tanggal:%d-%m-%Y}",
        })
    feed.sort(key=lambda k: k["waktu"], reverse=True)
    return feed[:KEGIATAN_MAKS]


def _sedang_dikerjakan(users):
    """Work started but not yet saved, newest first: inspections (auto-saved
    drafts, with how many parts already have a Kondisi), repairs and
    additions (PekerjaanAktif)."""
    from .models import DraftPemeriksaan, Laporan, PekerjaanAktif

    drafts = list(
        _milik(DraftPemeriksaan.objects.all(), "pemeriksa", users)
        .select_related("vehicle", "pemeriksa").order_by("-diperbarui_pada")[:SEDANG_MAKS]
    )
    lain = list(
        _milik(PekerjaanAktif.objects.all(), "user", users)
        .select_related("vehicle", "user").order_by("-dimulai_pada")[:SEDANG_MAKS]
    )
    nama = dict(
        Laporan.objects.filter(akun__in=[d.pemeriksa_id for d in drafts] + [p.user_id for p in lain])
        .order_by("dibuat_pada").values_list("akun_id", "nama")
    )
    hasil = []
    for d in drafts:
        cfg = golongan.for_vehicle(d.vehicle)
        total = len(cfg.form.alat) if cfg else 0
        terisi = sum(
            1 for k, v in (d.data or {}).items() if v and k.startswith("alat_") and k.endswith("_kondisi")
        )
        hasil.append({
            "jenis": "Pemeriksaan",
            "vehicle": d.vehicle,
            "pemeriksa": nama.get(d.pemeriksa_id) or d.pemeriksa.username,
            "waktu": d.diperbarui_pada,
            "terisi": min(terisi, total),
            "total": total,
            "persen": round(100 * min(terisi, total) / total) if total else 0,
        })
    for p in lain:
        hasil.append({
            "jenis": "Perbaikan" if p.jenis == PekerjaanAktif.Jenis.PERBAIKAN else "Penambahan",
            "vehicle": p.vehicle,
            # An addition has no vehicle yet, only the form (golongan) opened.
            "keterangan": p.keterangan,
            "pemeriksa": nama.get(p.user_id) or p.user.username,
            "waktu": p.dimulai_pada,
            "total": 0,
        })
    hasil.sort(key=lambda h: h["waktu"], reverse=True)
    return hasil[:SEDANG_MAKS]


def _berlangsung(kodes, users):
    """How many additions, inspections and repairs are under way right now
    (started, not saved) for the given vehicle groups."""
    from . import roles
    from .models import DraftPemeriksaan, PekerjaanAktif

    # An addition has no vehicle yet: its group is the form that was opened.
    label = [label for kode, label in roles.FORM_TAMBAH if kode in kodes]
    aktif = _milik(PekerjaanAktif.objects.all(), "user", users)
    draft = _milik(DraftPemeriksaan.objects.all(), "pemeriksa", users)
    return {
        "penambahan": aktif.filter(jenis=PekerjaanAktif.Jenis.PENAMBAHAN, keterangan__in=label).count(),
        "pemeriksaan": draft.filter(vehicle__group_kendaraan__in=kodes).count(),
        "perbaikan": aktif.filter(
            jenis=PekerjaanAktif.Jenis.PERBAIKAN, vehicle__group_kendaraan__in=kodes,
        ).count(),
    }


def konteks(users=None, halaman_kegiatan=1):
    hari_ini = timezone.localdate()
    sebulan = timezone.now() - timedelta(days=30)
    jadwal_aktif = (
        _milik(Jadwal.objects.all(), "vehicle__ditambahkan_oleh", users)
        .filter(status=Jadwal.Status.TERJADWAL).select_related("vehicle")
    )

    def pemeriksaan(cfgs):
        return sum(
            _milik(cfg.pemeriksaan_model.objects.all(), "pemeriksa__akun", users)
            .filter(dibuat_pada__gte=sebulan).count() for cfg in cfgs
        )

    def perbaikan(cfgs):
        return sum(
            _milik(cfg.perbaikan_model.objects.all(), "teknisi__akun", users)
            .filter(dibuat_pada__gte=sebulan).count() for cfg in cfgs
        )

    kendaraan_cfgs = [cfg for kode, cfg in golongan.GOLONGAN.items() if kode in KENDARAAN_KODE]
    non_kendaraan_cfgs = [cfg for kode, cfg in golongan.GOLONGAN.items() if kode in NON_KENDARAAN_KODE]

    return {
        "fleet_summary": _fleet_summary_group(list(Vehicle.GroupKendaraan.values), users),
        "fleet_summary_kendaraan": _fleet_summary_group(KENDARAAN_KODE, users),
        "fleet_summary_non_kendaraan": _fleet_summary_group(NON_KENDARAAN_KODE, users),
        "berlangsung_kendaraan": _berlangsung(KENDARAAN_KODE, users),
        "berlangsung_non_kendaraan": _berlangsung(NON_KENDARAAN_KODE, users),
        "pemeriksaan_30_hari": pemeriksaan(golongan.GOLONGAN.values()),
        "pemeriksaan_30_hari_kendaraan": pemeriksaan(kendaraan_cfgs),
        "pemeriksaan_30_hari_non_kendaraan": pemeriksaan(non_kendaraan_cfgs),
        "perbaikan_30_hari": perbaikan(golongan.GOLONGAN.values()),
        "perbaikan_30_hari_kendaraan": perbaikan(kendaraan_cfgs),
        "perbaikan_30_hari_non_kendaraan": perbaikan(non_kendaraan_cfgs),
        "jadwal_mendatang": list(jadwal_aktif.filter(tanggal__gte=hari_ini).order_by("tanggal", "id")[:5]),
        "jadwal_terlambat": list(jadwal_aktif.filter(tanggal__lt=hari_ini).order_by("tanggal", "id")[:5]),
        "jadwal_terlambat_kendaraan": list(
            jadwal_aktif.filter(tanggal__lt=hari_ini, vehicle__group_kendaraan__in=KENDARAAN_KODE).order_by("tanggal", "id")[:5]
        ),
        "jadwal_terlambat_non_kendaraan": list(
            jadwal_aktif.filter(tanggal__lt=hari_ini, vehicle__group_kendaraan__in=NON_KENDARAAN_KODE).order_by("tanggal", "id")[:5]
        ),
        "kegiatan_terbaru": Paginator(_kegiatan_terbaru(users), KEGIATAN_PER_HALAMAN).get_page(halaman_kegiatan),
        "sedang_dikerjakan": _sedang_dikerjakan(users),
    }


# --- Grafik tab: charts drawn as server-side SVG ---

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
LEBAR, TINGGI = 600, 240
KIRI, KANAN, ATAS, BAWAH = 76, 12, 16, 32


def _enam_bulan():
    hari_ini = timezone.localdate()
    bulan = []
    tahun, b = hari_ini.year, hari_ini.month
    for _ in range(6):
        bulan.append((tahun, b))
        b -= 1
        if b == 0:
            tahun, b = tahun - 1, 12
    return list(reversed(bulan))


def _per_bulan(qs, field, bulan, nilai=None):
    from django.db.models import Sum
    from django.db.models.functions import TruncMonth

    awal = timezone.make_aware(datetime(bulan[0][0], bulan[0][1], 1))
    if field == "tanggal":
        qs = qs.filter(tanggal__gte=awal.date())
    else:
        qs = qs.filter(**{f"{field}__gte": awal})
    agregat = Sum(nilai) if nilai else Count("id")
    hasil = {}
    for baris in qs.annotate(bln=TruncMonth(field)).values("bln").annotate(n=agregat):
        hasil[(baris["bln"].year, baris["bln"].month)] = baris["n"] or 0
    return [hasil.get(k, 0) for k in bulan]


def _atas_rapi(maks, minimum=4):
    """Smallest 1/2/4 x 10^k that is >= maks (at least ``minimum``): the midpoint tick stays a whole number."""
    batas = 1
    while True:
        for f in (1, 2, 4):
            if f * batas >= max(maks, minimum):
                return f * batas
        batas *= 10


def _batang(x, y, w, h, r=4):
    """Column path: 4px rounded data end, square at the baseline."""
    r = min(r, h, w / 2)
    dasar = y + h
    return (
        f"M{x:.1f},{dasar:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{dasar:.1f} Z"
    )


def _kolom(label_bulan, seri, format_nilai=str, minimum=4):
    """Grouped column chart geometry: seri = [(nama, kelas_css, [nilai per bulan]), ...]."""
    lebar_plot, tinggi_plot = LEBAR - KIRI - KANAN, TINGGI - ATAS - BAWAH
    atas = _atas_rapi(max((v for _, _, vals in seri for v in vals), default=0), minimum)
    pita = lebar_plot / len(label_bulan)
    tebal = min(24, (pita - 16) / len(seri))
    celah = 2
    total = len(seri) * tebal + (len(seri) - 1) * celah
    batang, label = [], []
    for i, nama_bulan in enumerate(label_bulan):
        tengah = KIRI + pita * i + pita / 2
        label.append({"x": round(tengah, 1), "teks": nama_bulan})
        for j, (nama, kelas, vals) in enumerate(seri):
            nilai = vals[i]
            h = tinggi_plot * nilai / atas
            x = tengah - total / 2 + j * (tebal + celah)
            y = ATAS + tinggi_plot - h
            batang.append({
                "path": _batang(x, y, tebal, h) if h > 0 else "",
                "kelas": kelas,
                "judul": f"{nama} · {nama_bulan}: {format_nilai(nilai)}",
                # Hit area covers the whole band column so small values are hoverable.
                "hit": {"x": round(x, 1), "w": round(tebal, 1)},
            })
    grid = [
        {"y": round(ATAS + tinggi_plot - tinggi_plot * t / atas, 1), "teks": format_nilai(t)}
        for t in (0, atas / 2, atas)
    ]
    return {
        "batang": batang, "label": label, "grid": grid, "lebar": LEBAR, "tinggi": TINGGI,
        "kiri": KIRI, "kanan": LEBAR - KANAN, "dasar": ATAS + tinggi_plot, "atas": ATAS, "tinggi_plot": tinggi_plot,
        "seri": [{"nama": n, "kelas": k} for n, k, _ in seri],
        "tabel": [
            {"bulan": b, "nilai": [format_nilai(vals[i]) for _, _, vals in seri]} for i, b in enumerate(label_bulan)
        ],
    }


def _bilangan(n):
    return str(int(n)) if float(n).is_integer() else f"{n:.1f}".replace(".", ",")


@_ingat
def _status_per_satuan(kodes, users):
    """The summary cards' numbers (Siap, Rusak Ringan, Rusak Berat, Sudah
    Diperbaiki, Perlu Servis) for every Satuan with vehicles in scope, the
    unit being that of whoever added the vehicle (their biodata), biggest
    first. Each number also comes split by vehicle group in ``rinci``
    ({card: {group code: n}}), for the table a card opens."""
    kunci = {
        Vehicle.Status.SIAP_PAKAI: "siap", Vehicle.Status.PERLU_SERVIS: "ringan",
        Vehicle.Status.DALAM_PERBAIKAN: "berat", Vehicle.Status.SUDAH_DIPERBAIKI: "diperbaiki",
    }
    kartu = ("total", "siap", "ringan", "berat", "diperbaiki", "servis")
    qs = _kendaraan(users).filter(group_kendaraan__in=kodes)
    baris = {}

    def tambah(nama, kolom, golongan, n):
        b = baris.setdefault(nama or TANPA_SATUAN, {
            "nama": nama or TANPA_SATUAN, **dict.fromkeys(kartu, 0), "rinci": {k: {} for k in kartu},
        })
        b[kolom] += n
        b["rinci"][kolom][golongan] = b["rinci"][kolom].get(golongan, 0) + n

    per = qs.order_by().values_list("penambah__satuan__nama", "status", "group_kendaraan").annotate(n=Count("id"))
    for nama, status, golongan_kode, n in per:
        tambah(nama, "total", golongan_kode, n)
        if status in kunci:
            tambah(nama, kunci[status], golongan_kode, n)
    # Not a status: a vehicle can be due a service whatever its condition.
    servis = list(_perlu_servis(kodes, users))
    if servis:
        per = (
            qs.filter(pk__in=servis).order_by()
            .values_list("penambah__satuan__nama", "group_kendaraan").annotate(n=Count("id"))
        )
        for nama, golongan_kode, n in per:
            tambah(nama, "servis", golongan_kode, n)
    return sorted(baris.values(), key=lambda b: (-b["total"], b["nama"]))


# Units drawn on the Grafik tab's per-Satuan chart; its table lists them all.
SATUAN_GRAFIK_MAKS = 8


@_ingat
def _per_satuan(cfgs, bulan, users):
    """Inspections and repairs of the chart's six months per Satuan (the unit
    of the inspector's / technician's biodata), busiest first: grouped bars
    for the SATUAN_GRAFIK_MAKS busiest and a table of every unit."""
    awal = timezone.make_aware(datetime(bulan[0][0], bulan[0][1], 1))
    jumlah = {}  # unit name -> [inspections, repairs]
    for cfg in cfgs:
        for i, (model, orang) in enumerate((
            (cfg.pemeriksaan_model, "pemeriksa"), (cfg.perbaikan_model, "teknisi"),
        )):
            qs = _milik(model.objects.filter(dibuat_pada__gte=awal), f"{orang}__akun", users)
            for nama, n in qs.order_by().values_list(f"{orang}__satuan__nama").annotate(n=Count("id")):
                jumlah.setdefault(nama or "Tanpa satuan", [0, 0])[i] += n
    tabel = sorted(
        ({"nama": nama, "pemeriksaan": a, "perbaikan": b, "total": a + b} for nama, (a, b) in jumlah.items()),
        key=lambda t: (-t["total"], t["nama"]),
    )
    digambar = tabel[:SATUAN_GRAFIK_MAKS]
    maks = max((max(t["pemeriksaan"], t["perbaikan"]) for t in digambar), default=0) or 1
    lebar_label, ujung = 230, LEBAR - 40

    def batang(n, y):
        w = (ujung - lebar_label) * n / maks
        return {"nilai": n, "y": y, "path": _batang_horizontal(lebar_label, y, w, 13) if n else "", "x_nilai": round(lebar_label + w + 6, 1)}

    return {
        "baris": [
            {
                "label": t["nama"] if len(t["nama"]) <= 30 else t["nama"][:29] + "…", "nama": t["nama"],
                "y": 6 + i * 44, "pemeriksaan": batang(t["pemeriksaan"], 6 + i * 44),
                "perbaikan": batang(t["perbaikan"], 6 + i * 44 + 15),
            }
            for i, t in enumerate(digambar)
        ],
        "tinggi": 6 + len(digambar) * 44, "lebar": LEBAR, "x0": lebar_label,
        "tabel": tabel, "lainnya": len(tabel) - len(digambar),
        "total": {
            "pemeriksaan": sum(t["pemeriksaan"] for t in tabel), "perbaikan": sum(t["perbaikan"] for t in tabel),
            "total": sum(t["total"] for t in tabel),
        },
    }


@_ingat
def _grafik_untuk_grup(cfgs, vehicle_kodes, label_bulan, bulan, users):
    pemeriksaan = [0] * 6
    perbaikan = [0] * 6
    for cfg in cfgs:
        pemeriksaan = [a + b for a, b in zip(pemeriksaan, _per_bulan(_milik(cfg.pemeriksaan_model.objects.all(), "pemeriksa__akun", users), "dibuat_pada", bulan))]
        perbaikan = [a + b for a, b in zip(perbaikan, _per_bulan(_milik(cfg.perbaikan_model.objects.all(), "teknisi__akun", users), "dibuat_pada", bulan))]

    per_golongan = dict(
        _kendaraan(users).filter(group_kendaraan__in=vehicle_kodes).values_list("group_kendaraan").annotate(n=Count("id"))
    )
    baris = [(label, per_golongan.get(kode, 0)) for kode, label in Vehicle.GroupKendaraan.choices if kode in vehicle_kodes]
    maks = max((n for _, n in baris), default=0) or 1
    lebar_label, ujung = 170, LEBAR - 48
    golongan_bar = [
        {
            "label": label, "nilai": n, "y": 8 + i * 40,
            "path": _batang_horizontal(lebar_label, 8 + i * 40, (ujung - lebar_label) * n / maks, 24) if n else "",
            "x_nilai": round(lebar_label + (ujung - lebar_label) * n / maks + 8, 1),
        }
        for i, (label, n) in enumerate(baris)
    ]
    return {
        "aktivitas": _kolom(label_bulan, [
            ("Pemeriksaan", "seri-1", pemeriksaan),
            ("Perbaikan", "seri-2", perbaikan),
        ], _bilangan),
        "golongan": {"bar": golongan_bar, "tinggi": 8 + len(baris) * 40, "lebar": LEBAR, "x0": lebar_label},
        "satuan": _per_satuan(cfgs, bulan, users),
        "status_satuan": _status_per_satuan(vehicle_kodes, users),
    }


def grafik(users=None):
    bulan = _enam_bulan()
    label_bulan = [f"{BULAN[b - 1]} {str(t)[2:]}" for t, b in bulan]

    all_cfgs = list(golongan.GOLONGAN.values())
    all_kode = [kode for kode, _ in Vehicle.GroupKendaraan.choices]  # all groups
    kendaraan_cfgs = [cfg for kode, cfg in golongan.GOLONGAN.items() if kode in KENDARAAN_KODE]
    non_kendaraan_cfgs = [cfg for kode, cfg in golongan.GOLONGAN.items() if kode in NON_KENDARAAN_KODE]

    semua = _grafik_untuk_grup(all_cfgs, all_kode, label_bulan, bulan, users)
    kendaraan = _grafik_untuk_grup(kendaraan_cfgs, KENDARAAN_KODE, label_bulan, bulan, users)
    non_kendaraan = _grafik_untuk_grup(non_kendaraan_cfgs, NON_KENDARAAN_KODE, label_bulan, bulan, users)

    return {
        **semua,
        "kendaraan": kendaraan,
        "non_kendaraan": non_kendaraan,
    }


def _batang_horizontal(x, y, w, h, r=4):
    """Bar path: square at the baseline (left), 4px rounded data end (right)."""
    r = min(r, w, h / 2)
    return (
        f"M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z"
    )
