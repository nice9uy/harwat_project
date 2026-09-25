"""Laporan menus: inspections, repairs and vehicles added, across all vehicle groups.

Each report filters by date range and vehicle group, shows a paged table and
offers the same rows as an Excel download (?unduh=excel).
"""
from datetime import date
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render
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


def _render(request, template, judul, header, rows, f, nama_file):
    if request.GET.get("unduh") == "excel":
        return _excel(judul, header, rows, f, nama_file)
    halaman = halaman_dari(request, rows)
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
                hasil.vehicle.nopol,
                hasil.vehicle.merek,
                Vehicle.GroupKendaraan(kode).label,
                f"{hasil.pemeriksa.nama} ({hasil.pemeriksa.pangkat})",
                hasil.jumlah_item - hasil.jumlah_perlu,
                hasil.jumlah_perlu,
            ))
    rows.sort(key=lambda r: r[0], reverse=True)
    rows = [(r[0].strftime("%d-%m-%Y %H:%M"),) + r[1:] for r in rows]
    header = ["Tanggal", "No. Registrasi", "Merk/Type", "Golongan", "Pemeriksa", "Item Baik", "Item Perlu Perbaikan"]
    return _render(request, "accounts/laporan_tabel.html", "Laporan Pemeriksaan", header, rows, f, "laporan-pemeriksaan.xlsx")


@login_required
def laporan_perbaikan(request):
    f = _filter(request)
    rows = []
    for kode, cfg in _golongan_dipilih(f):
        qs = cfg.perbaikan_model.objects.select_related("item__pemeriksaan__vehicle", "teknisi").order_by()
        for p in _rentang(qs, "dibuat_pada", f):
            vehicle = p.item.pemeriksaan.vehicle
            rows.append((
                p.dibuat_pada,
                vehicle.nopol,
                Vehicle.GroupKendaraan(kode).label,
                f"{p.item.nomor}. {p.item.nama_alat}",
                p.item.get_kondisi_display(),
                p.get_kondisi_display(),
                f"{p.teknisi.nama} ({p.teknisi.pangkat})",
                p.keterangan,
            ))
    rows.sort(key=lambda r: r[0], reverse=True)
    rows = [(r[0].strftime("%d-%m-%Y %H:%M"),) + r[1:] for r in rows]
    header = ["Tanggal", "No. Registrasi", "Golongan", "Komponen", "Kondisi Awal", "Kondisi Setelah", "Teknisi", "Keterangan"]
    return _render(request, "accounts/laporan_tabel.html", "Laporan Perbaikan", header, rows, f, "laporan-perbaikan.xlsx")


@login_required
def laporan_penambahan(request):
    f = _filter(request)
    qs = Vehicle.objects.order_by("-dibuat_pada", "-id")
    if f["golongan"]:
        qs = qs.filter(group_kendaraan=f["golongan"])
    qs = _rentang(qs, "dibuat_pada", f)
    rows = [
        (
            v.dibuat_pada.strftime("%d-%m-%Y %H:%M") if v.dibuat_pada else "-",
            v.nopol, v.merek, v.get_group_kendaraan_display(), v.no_chasis or "-", v.no_mesin or "-",
        )
        for v in qs
    ]
    header = ["Ditambahkan", "No. Registrasi", "Merk/Type", "Golongan", "No. Chasis", "No. Mesin"]
    return _render(
        request, "accounts/laporan_tabel.html", "Laporan Penambahan Kendaraan/Barang", header, rows, f,
        "laporan-penambahan-kendaraan.xlsx",
    )
