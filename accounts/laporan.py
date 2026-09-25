"""Laporan menus: inspections, repairs and vehicles added, across all vehicle groups.

Each report filters by date range and vehicle group, shows a paged table and
offers the same rows as an Excel download (?unduh=excel).
"""
from datetime import date
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from fleet.models import Vehicle

from . import golongan
from .paging import halaman as halaman_dari

def _tanggal(raw):
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _filter(request):
    grup = request.GET.get("golongan", "")
    return {
        "dari": _tanggal(request.GET.get("dari")),
        "sampai": _tanggal(request.GET.get("sampai")),
        "golongan": grup if grup in Vehicle.GroupKendaraan.values else "",
    }


def _rentang(qs, field, f):
    if f["dari"]:
        qs = qs.filter(**{f"{field}__date__gte": f["dari"]})
    if f["sampai"]:
        qs = qs.filter(**{f"{field}__date__lte": f["sampai"]})
    return qs


def _golongan_dipilih(f):
    """Registry entries of the groups in the report (all groups with a form, or the chosen one)."""
    return [(kode, cfg) for kode, cfg in golongan.GOLONGAN.items() if not f["golongan"] or kode == f["golongan"]]


def _keterangan_filter(f):
    bagian = []
    if f["dari"] or f["sampai"]:
        dari = f["dari"].strftime("%d-%m-%Y") if f["dari"] else "awal"
        sampai = f["sampai"].strftime("%d-%m-%Y") if f["sampai"] else "sekarang"
        bagian.append(f"Periode {dari} s/d {sampai}")
    bagian.append(Vehicle.GroupKendaraan(f["golongan"]).label if f["golongan"] else "Semua golongan")
    return " · ".join(bagian)


def _excel(judul, header, rows, f, nama_file):
    """The report as an .xlsx sheet: title, filter line, styled header, data."""
    wb = Workbook()
    ws = wb.active
    ws.title = judul[:31].replace("/", "-")
    ws.append([judul])
    ws.append([f"{_keterangan_filter(f)} · dicetak {timezone.localtime():%d-%m-%Y %H:%M}"])
    ws.append([])
    ws.append(["No"] + header)
    for nomor, baris in enumerate(rows, start=1):
        ws.append([nomor] + list(baris))

    ws["A1"].font = Font(bold=True, size=14, color="0B1F3A")
    ws["A2"].font = Font(italic=True, color="5B6579")
    header_row = 4
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0B1F3A")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(header) + 1)}{header_row + len(rows)}"
    for kolom in range(1, len(header) + 2):
        panjang = max(
            len(str(ws.cell(row=r, column=kolom).value or "")) for r in range(header_row, header_row + len(rows) + 1)
        )
        ws.column_dimensions[get_column_letter(kolom)].width = min(max(panjang + 2, 6), 50)

    buffer = BytesIO()
    wb.save(buffer)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{nama_file}"'
    return response


def _render(
    request, template, judul, header, rows, f, nama_file, tautan=None, kolom_tanggal=1, kolom_utama=2,
    pakai_tanggal=True, pakai_cari=False,
):
    """``tautan``: optional per-row URL (same order as ``rows``) opened in the detail modal.
    ``kolom_tanggal`` / ``kolom_utama``: 1-based columns styled as the date and as
    the row's key (No. Registrasi); 0 for none. ``pakai_tanggal``: show the date filter;
    ``pakai_cari``: show the search field (``?q=``)."""
    if request.GET.get("unduh") == "excel":
        return _excel(judul, header, rows, f, nama_file)
    halaman = halaman_dari(request, list(zip(rows, tautan or [None] * len(rows))))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, template, {
        "judul": judul,
        "header": header,
        "halaman": halaman,
        "total": len(rows),
        "f": f,
        "golongan_pilihan": Vehicle.GroupKendaraan.choices,
        "query": query.urlencode(),
        "kolom_tanggal": kolom_tanggal,
        "kolom_utama": kolom_utama,
        "pakai_tanggal": pakai_tanggal,
        "pakai_cari": pakai_cari,
        "q": request.GET.get("q", "").strip(),
    })


def _cari_kendaraan(qs, q):
    if q:
        qs = qs.filter(
            Q(nopol__icontains=q) | Q(merek__icontains=q) | Q(no_chasis__icontains=q) | Q(no_mesin__icontains=q)
        )
    return qs


def _laporan_per_kendaraan(request, judul, kendaraan, detail, nama_file):
    """A report with one row per vehicle (``kendaraan``: in display order), a
    search field and no date filter; each row opens the ``detail`` modal."""
    f = _filter(request)
    tautan = [reverse(detail, args=[v.pk]) for v in kendaraan]
    rows = [
        (v.nopol, v.merek, v.no_chasis or "-", v.no_mesin or "-", v.get_group_kendaraan_display())
        for v in kendaraan
    ]
    header = ["No. Registrasi", "Merk/Type", "No. Chasis", "No. Mesin", "Golongan"]
    return _render(
        request, "accounts/laporan_tabel.html", judul, header, rows, f, nama_file,
        tautan=tautan, kolom_tanggal=0, kolom_utama=1, pakai_tanggal=False, pakai_cari=True,
    )


def _kendaraan_dengan_catatan(request, model_dari_cfg, relasi_kendaraan):
    """Vehicles with at least one record (inspection or repair) in the chosen
    group and matching the search, newest record first."""
    f = _filter(request)
    terakhir = {}  # vehicle id -> newest record time
    for _, cfg in _golongan_dipilih(f):
        qs = model_dari_cfg(cfg).objects.order_by().values(relasi_kendaraan).annotate(waktu=Max("dibuat_pada"))
        for baris in qs:
            vid = baris[relasi_kendaraan]
            terakhir[vid] = max(baris["waktu"], terakhir.get(vid, baris["waktu"]))
    qs = _cari_kendaraan(Vehicle.objects.filter(pk__in=list(terakhir)), request.GET.get("q", "").strip())
    return sorted(qs, key=lambda v: (terakhir[v.pk], v.pk), reverse=True)


@login_required
def laporan_pemeriksaan(request):
    """One row per inspected vehicle; the row's modal lists the inspections."""
    kendaraan = _kendaraan_dengan_catatan(request, lambda cfg: cfg.pemeriksaan_model, "vehicle")
    return _laporan_per_kendaraan(
        request, "Laporan Pemeriksaan", kendaraan, "accounts:laporan_pemeriksaan_detail", "laporan-pemeriksaan.xlsx",
    )


@login_required
def laporan_perbaikan(request):
    """One row per repaired vehicle; the row's modal lists the repairs."""
    kendaraan = _kendaraan_dengan_catatan(request, lambda cfg: cfg.perbaikan_model, "item__pemeriksaan__vehicle")
    return _laporan_per_kendaraan(
        request, "Laporan Perbaikan", kendaraan, "accounts:laporan_perbaikan_detail", "laporan-perbaikan.xlsx",
    )


@login_required
def laporan_penambahan(request):
    """Every vehicle, newest added first; the row's modal shows it and who added it."""
    f = _filter(request)
    qs = Vehicle.objects.order_by("-dibuat_pada", "-id")
    if f["golongan"]:
        qs = qs.filter(group_kendaraan=f["golongan"])
    kendaraan = list(_cari_kendaraan(qs, request.GET.get("q", "").strip()))
    return _laporan_per_kendaraan(
        request, "Laporan Penambahan Kendaraan/Barang", kendaraan, "accounts:laporan_penambahan_detail",
        "laporan-penambahan-kendaraan.xlsx",
    )


@login_required
def laporan_pemeriksaan_detail(request, pk):
    """Modal for a Laporan Pemeriksaan row: every inspection of that vehicle
    (the clicked one highlighted) and the personnel who inspected it."""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    cfg = golongan.for_vehicle(vehicle)
    riwayat = []
    if cfg is not None:
        riwayat = list(
            cfg.pemeriksaan_model.objects.filter(vehicle=vehicle)
            .select_related("pemeriksa__satuan")
            .annotate(
                jumlah_item=Count("items"),
                jumlah_perlu=Count("items", filter=~Q(items__kondisi__in=cfg.baik)),
            )
            .order_by("-dibuat_pada", "-id")
        )
    for hasil in riwayat:
        hasil.jumlah_baik = hasil.jumlah_item - hasil.jumlah_perlu
    return render(request, "accounts/_laporan_pemeriksaan_detail.html", {
        "vehicle": vehicle,
        "riwayat": riwayat,
        "personil": _per_orang(riwayat, "pemeriksa"),
        "dipilih": _id_dipilih(request, "pemeriksaan"),
        "tab": "personil" if request.GET.get("tab") == "personil" else "riwayat",
    })


def _per_orang(daftar, atribut):
    """One row per person (by NIP) from records whose ``atribut`` is a biodata:
    each record saves its own biodata, so the newest one is shown with how
    often and when that person last appears. ``daftar`` is newest first."""
    orang = {}
    for obj in daftar:
        biodata = getattr(obj, atribut)
        baris = orang.setdefault(biodata.nip, {"biodata": biodata, "terakhir": obj.dibuat_pada, "jumlah": 0})
        baris["jumlah"] += 1
    return list(orang.values())


def _id_dipilih(request, param):
    try:
        return int(request.GET.get(param, ""))
    except ValueError:
        return None


@login_required
def laporan_perbaikan_detail(request, pk):
    """Modal for a Laporan Perbaikan row: every repair of that vehicle (the
    clicked one highlighted) and the personnel who repaired it."""
    vehicle = get_object_or_404(Vehicle, pk=pk)
    cfg = golongan.for_vehicle(vehicle)
    riwayat = []
    if cfg is not None:
        riwayat = list(
            cfg.perbaikan_model.objects.filter(item__pemeriksaan__vehicle=vehicle)
            .select_related("item", "teknisi__satuan")
            .order_by("-dibuat_pada", "-id")
        )
    return render(request, "accounts/_laporan_perbaikan_detail.html", {
        "vehicle": vehicle,
        "riwayat": riwayat,
        "personil": _per_orang(riwayat, "teknisi"),
        "dipilih": _id_dipilih(request, "perbaikan"),
    })


@login_required
def laporan_penambahan_detail(request, pk):
    """Modal for a Laporan Penambahan row: the vehicle's data, photos and QR
    code, and who added it."""
    vehicle = get_object_or_404(
        Vehicle.objects.select_related("ditambahkan_oleh", "penambah__satuan").prefetch_related("fotos"), pk=pk,
    )
    # Same table as the other modals' personnel tab, with the account in the
    # count column and the time added in the "last" column.
    penambah_baris = [{
        "biodata": vehicle.penambah,
        "jumlah": vehicle.ditambahkan_oleh.username if vehicle.ditambahkan_oleh else "-",
        "terakhir": vehicle.dibuat_pada,
    }] if vehicle.penambah else []
    return render(request, "accounts/_laporan_penambahan_detail.html", {
        "vehicle": vehicle, "penambah_baris": penambah_baris,
    })

