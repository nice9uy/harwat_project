"""Dashboard data: fleet counts, schedule and a feed of the latest activities."""
from datetime import datetime, timedelta

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


def _rupiah_singkat(n):
    n = int(n)
    if n >= 1_000_000:
        return f"Rp {n / 1_000_000:.1f} jt".replace(".0 jt", " jt").replace(".", ",")
    if n >= 1_000:
        return f"Rp {n // 1_000} rb"
    return f"Rp {n}"


def _bilangan(n):
    return str(int(n)) if float(n).is_integer() else f"{n:.1f}".replace(".", ",")


def grafik():
    from fleet.models import Servis

    bulan = _enam_bulan()
    label_bulan = [f"{BULAN[b - 1]} {str(t)[2:]}" for t, b in bulan]
    pemeriksaan = [0] * 6
    perbaikan = [0] * 6
    for cfg in golongan.GOLONGAN.values():
        pemeriksaan = [a + b for a, b in zip(pemeriksaan, _per_bulan(cfg.pemeriksaan_model.objects, "dibuat_pada", bulan))]
        perbaikan = [a + b for a, b in zip(perbaikan, _per_bulan(cfg.perbaikan_model.objects, "dibuat_pada", bulan))]
    biaya = _per_bulan(Servis.objects, "tanggal", bulan, nilai="biaya")

    per_golongan = dict(Vehicle.objects.values_list("group_kendaraan").annotate(n=Count("id")))
    baris = [(label, per_golongan.get(kode, 0)) for kode, label in Vehicle.GroupKendaraan.choices]
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
        "biaya": _kolom(label_bulan, [("Biaya servis", "seri-1", biaya)], _rupiah_singkat, minimum=1_000_000),
        "golongan": {"bar": golongan_bar, "tinggi": 8 + len(baris) * 40, "lebar": LEBAR, "x0": lebar_label},
        "total_biaya": sum(biaya),
    }


def _batang_horizontal(x, y, w, h, r=4):
    """Bar path: square at the baseline (left), 4px rounded data end (right)."""
    r = min(r, w, h / 2)
    return (
        f"M{x:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z"
    )
