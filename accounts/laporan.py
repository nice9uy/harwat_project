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
    pakai_tanggal=True,
):
    """``tautan``: optional per-row URL (same order as ``rows``) opened in the detail modal.
    ``kolom_tanggal`` / ``kolom_utama``: 1-based columns styled as the date and as
    the row's key (No. Registrasi); 0 for none. ``pakai_tanggal``: show the date filter."""
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
    })


@login_required
def laporan_pemeriksaan(request):
    f = _filter(request)
    rows = []
    for kode, cfg in _golongan_dipilih(f):
        qs = (
            cfg.pemeriksaan_model.objects.select_related("vehicle", "pemeriksa")
            .annotate(
                jumlah_item=Count("items"),
                jumlah_perlu=Count("items", filter=~Q(items__kondisi__in=cfg.baik)),
            )
            .order_by()
        )
        for hasil in _rentang(qs, "dibuat_pada", f):
            rows.append((
                hasil.dibuat_pada,
                f"{reverse('accounts:laporan_pemeriksaan_detail', args=[hasil.vehicle_id])}?pemeriksaan={hasil.pk}",
                hasil.vehicle.nopol,
                hasil.vehicle.merek,
                Vehicle.GroupKendaraan(kode).label,
                f"{hasil.pemeriksa.nama} ({hasil.pemeriksa.pangkat})",
                hasil.jumlah_item - hasil.jumlah_perlu,
                hasil.jumlah_perlu,
            ))
    rows.sort(key=lambda r: r[0], reverse=True)
    tautan = [r[1] for r in rows]
    rows = [(timezone.localtime(r[0]).strftime("%d-%m-%Y %H:%M"),) + r[2:] for r in rows]
    header = ["Tanggal", "No. Registrasi", "Merk/Type", "Golongan", "Pemeriksa", "Item Baik", "Item Perlu Perbaikan"]
    return _render(
        request, "accounts/laporan_tabel.html", "Laporan Pemeriksaan", header, rows, f, "laporan-pemeriksaan.xlsx",
        tautan=tautan,
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


@login_required
def laporan_perbaikan(request):
    """One row per vehicle repaired in the period (newest repair first); the
    row's modal lists the repairs themselves. No date filter: all repairs count."""
    f = {**_filter(request), "dari": None, "sampai": None}
    terakhir = {}  # vehicle id -> newest repair time
    for _, cfg in _golongan_dipilih(f):
        qs = _rentang(cfg.perbaikan_model.objects.all(), "dibuat_pada", f)
        for baris in qs.order_by().values("item__pemeriksaan__vehicle").annotate(waktu=Max("dibuat_pada")):
            vid = baris["item__pemeriksaan__vehicle"]
            terakhir[vid] = max(baris["waktu"], terakhir.get(vid, baris["waktu"]))
    kendaraan = Vehicle.objects.in_bulk(list(terakhir))
    urut = sorted(kendaraan.values(), key=lambda v: (terakhir[v.pk], v.pk), reverse=True)
    tautan = [reverse("accounts:laporan_perbaikan_detail", args=[v.pk]) for v in urut]
    rows = [
        (v.nopol, v.merek, v.no_chasis or "-", v.no_mesin or "-", v.get_group_kendaraan_display())
        for v in urut
    ]
    header = ["No. Registrasi", "Merk/Type", "No. Chasis", "No. Mesin", "Golongan"]
    return _render(
        request, "accounts/laporan_tabel.html", "Laporan Perbaikan", header, rows, f, "laporan-perbaikan.xlsx",
        tautan=tautan, kolom_tanggal=0, kolom_utama=1, pakai_tanggal=False,
    )


@login_required
def laporan_penambahan(request):
    f = _filter(request)
    qs = Vehicle.objects.order_by("-dibuat_pada", "-id")
    if f["golongan"]:
        qs = qs.filter(group_kendaraan=f["golongan"])
    qs = list(_rentang(qs, "dibuat_pada", f))
    tautan = [reverse("accounts:laporan_penambahan_detail", args=[v.pk]) for v in qs]
    rows = [
        (
            v.nopol, v.merek, v.get_group_kendaraan_display(), v.no_chasis or "-", v.no_mesin or "-",
        )
        for v in qs
    ]
    header = ["No. Registrasi", "Merk/Type", "Golongan", "No. Chasis", "No. Mesin"]
    return _render(
        request, "accounts/laporan_tabel.html", "Laporan Penambahan Kendaraan/Barang", header, rows, f,
        "laporan-penambahan-kendaraan.xlsx", tautan=tautan, kolom_tanggal=0, kolom_utama=1,
    )


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

