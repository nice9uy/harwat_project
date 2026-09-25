"""Laporan menus: inspections, repairs and vehicles added, across all vehicle groups.

Each report filters by date range and vehicle group, shows a paged table and
offers the same rows as a CSV download (?unduh=csv).
"""
import csv
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import render

from fleet.models import Vehicle

from . import golongan

PER_HALAMAN = 50


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


def _csv(nama_file, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nama_file}"'
    response.write("﻿")  # BOM so Excel reads the UTF-8 file correctly
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    return response


def _render(request, template, judul, header, rows, f, nama_csv):
    if request.GET.get("unduh") == "csv":
        return _csv(nama_csv, header, rows)
    halaman = Paginator(rows, PER_HALAMAN).get_page(request.GET.get("page"))
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
    return _render(request, "accounts/laporan_tabel.html", "Laporan Pemeriksaan", header, rows, f, "laporan-pemeriksaan.csv")


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
    return _render(request, "accounts/laporan_tabel.html", "Laporan Perbaikan", header, rows, f, "laporan-perbaikan.csv")


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
        "laporan-penambahan-kendaraan.csv",
    )
