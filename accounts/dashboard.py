"""Dashboard data: fleet counts, schedule and a feed of the latest activities."""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from fleet.models import Jadwal, Servis, Vehicle
from fleet.services import get_fleet_summary

from . import golongan

KEGIATAN_MAKS = 15


def _kegiatan_terbaru():
    """Latest inspections, repairs, vehicles added, services and schedules, newest first.

    Each source is one query (limited to KEGIATAN_MAKS), so the feed's cost
    doesn't grow with the data.
    """
    feed = []
    for kode, cfg in golongan.GOLONGAN.items():
        label = Vehicle.GroupKendaraan(kode).label
        inspeksi = (
            cfg.pemeriksaan_model.objects.select_related("vehicle", "pemeriksa")
            .annotate(perlu=Count("items", filter=~Q(items__kondisi__in=cfg.baik)))
            .order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]
        )
        for h in inspeksi:
            feed.append({
                "waktu": h.dibuat_pada, "jenis": "pemeriksaan", "oleh": h.pemeriksa.nama,
                "teks": f"memeriksa {h.vehicle.nopol} ({label})",
                "detail": f"{h.perlu} item perlu perbaikan" if h.perlu else "Semua item baik",
            })
        perbaikan = cfg.perbaikan_model.objects.select_related("teknisi", "item__pemeriksaan__vehicle").order_by(
            "-dibuat_pada", "-id"
        )[:KEGIATAN_MAKS]
        for p in perbaikan:
            feed.append({
                "waktu": p.dibuat_pada, "jenis": "perbaikan", "oleh": p.teknisi.nama,
                "teks": f"memperbaiki {p.item.nama_alat} pada {p.item.pemeriksaan.vehicle.nopol}",
                "detail": f"Kondisi sekarang: {p.get_kondisi_display()}",
            })
    for v in Vehicle.objects.exclude(dibuat_pada=None).order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": v.dibuat_pada, "jenis": "kendaraan", "oleh": "",
            "teks": f"Kendaraan {v.nopol} ({v.merek}) ditambahkan",
            "detail": v.get_group_kendaraan_display(),
        })
    for s in Servis.objects.select_related("vehicle").order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": s.dibuat_pada, "jenis": "servis", "oleh": "",
            "teks": f"Servis {s.jenis_servis} untuk {s.vehicle.nopol} dicatat",
            "detail": s.bengkel or "",
        })
    for j in Jadwal.objects.select_related("vehicle").order_by("-dibuat_pada", "-id")[:KEGIATAN_MAKS]:
        feed.append({
            "waktu": j.dibuat_pada, "jenis": "jadwal", "oleh": "",
            "teks": f"Jadwal {j.get_kegiatan_display().lower()} {j.vehicle.nopol} dibuat",
            "detail": f"Untuk {j.tanggal:%d-%m-%Y}",
        })
    feed.sort(key=lambda k: k["waktu"], reverse=True)
    return feed[:KEGIATAN_MAKS]


def konteks():
    hari_ini = timezone.localdate()
    sebulan = timezone.now() - timedelta(days=30)
    jadwal_aktif = Jadwal.objects.filter(status=Jadwal.Status.TERJADWAL).select_related("vehicle")
    return {
        "fleet_summary": get_fleet_summary(),
        "pemeriksaan_30_hari": sum(
            cfg.pemeriksaan_model.objects.filter(dibuat_pada__gte=sebulan).count() for cfg in golongan.GOLONGAN.values()
        ),
        "perbaikan_30_hari": sum(
            cfg.perbaikan_model.objects.filter(dibuat_pada__gte=sebulan).count() for cfg in golongan.GOLONGAN.values()
        ),
        "jadwal_mendatang": list(jadwal_aktif.filter(tanggal__gte=hari_ini).order_by("tanggal", "id")[:5]),
        "jadwal_terlambat": list(jadwal_aktif.filter(tanggal__lt=hari_ini).order_by("tanggal", "id")[:5]),
        "kegiatan_terbaru": _kegiatan_terbaru(),
    }
