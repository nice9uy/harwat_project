"""Laporan menus: inspections, repairs and vehicles added, across all vehicle groups.

Each report filters by vehicle group and by the Satuan of whoever did the
work, and shows a paged table. (Laporan Tim, in laporan_tim.py, reuses the
table and also offers it as an Excel download, ?unduh=excel.)
"""
import uuid
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


def _satuan(raw):
    """The Satuan with public uuid ``raw`` (the ?satuan= filter), or None."""
    from .models import Satuan

    try:
        return Satuan.objects.filter(uuid=uuid.UUID(raw or "")).first()
    except ValueError:
        return None


def _filter(request):
    grup = request.GET.get("golongan", "")
    return {
        "dari": _tanggal(request.GET.get("dari")),
        "sampai": _tanggal(request.GET.get("sampai")),
        "golongan": grup if grup in Vehicle.GroupKendaraan.values else "",
        # The unit of whoever did the work (their biodata's Satuan).
        "satuan": _satuan(request.GET.get("satuan")),
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
    if f.get("satuan"):
        bagian.append(f"Satuan {f['satuan'].nama}")
    return " · ".join(bagian)


def teks_saja(ws):
    """Typed text stays text: openpyxl would write a cell starting with "="
    (a Keterangan, a Merk/Type) as a formula that Excel runs on opening."""
    for baris in ws.iter_rows():
        for sel in baris:
            if sel.data_type == "f":
                sel.data_type = "s"


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
    teks_saja(ws)

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


def _pilihan_satuan():
    """The units a report can be narrowed to: those someone belongs to (a
    report's unit is always somebody's biodata's), not all the thousands."""
    from .models import Satuan

    return list(Satuan.objects.filter(biodata__isnull=False).distinct().order_by("nama"))


def opsi_satuan(daftar):
    """``daftar`` (Satuan) as the options of the type-ahead Satuan filter."""
    return [{"v": str(s.uuid), "l": s.nama} for s in daftar]


def _render(
    request, template, judul, header, rows, f, nama_file, tautan=None, kolom_tanggal=1, kolom_utama=2,
    pakai_tanggal=True, pakai_cari=False, pakai_excel=True, pakai_satuan=False, pakai_filter=True, pakai_hapus=False, pakai_qr=False,
    pakai_ekspor_qr=False, tab=None, kondisi_pilihan=None, pakai_pdf=False, per_halaman=None,
):
    """``tautan``: optional per-row URL (same order as ``rows``) opened in the detail modal.
    ``kolom_tanggal`` / ``kolom_utama``: 1-based columns styled as the date and as
    the row's key (No. Registrasi); 0 for none. ``pakai_tanggal``: show the date filter;
    ``pakai_cari``: show the search field (``?q=``); ``pakai_excel``: offer the
    Excel download (``nama_file``); ``pakai_satuan``: show the Satuan filter;
    ``pakai_filter``: show the filter box at all. ``tab``: the report's tabs
    above the table, [(kode, label)], the one shown being ``?tab=``."""
    if pakai_excel and request.GET.get("unduh") == "excel":
        return _excel(judul, header, rows, f, nama_file)
    halaman = halaman_dari(
        request, list(zip(rows, tautan or [None] * len(rows))), **({"per_halaman": per_halaman} if per_halaman else {}),
    )
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
        "pakai_excel": pakai_excel,
        "pakai_filter": pakai_filter,
        "pakai_hapus": pakai_hapus,
        "pakai_qr": pakai_qr,
        "pakai_ekspor_qr": pakai_ekspor_qr,
        "satuan_pilihan": pakai_satuan,
        "satuan_opsi": opsi_satuan(_pilihan_satuan()) if pakai_satuan else [],
        "q": request.GET.get("q", "").strip(),
        "tab": tab or [],
        # A Kondisi filter (?kondisi=): [(kode, label)], the one picked in f["kondisi"].
        "kondisi_pilihan": kondisi_pilihan or [],
        # An "Export ke PDF" button (?unduh=pdf), handled by the report's own view.
        "pakai_pdf": pakai_pdf,
        "tab_aktif": _tab(request, tab) if tab else "",
    })


def _tab(request, tab):
    """The tab picked (?tab=) of a report's ``tab`` [(kode, label)]; without
    one, Kendaraan (what the report listed before it had tabs) or the first."""
    kode = request.GET.get("tab", "")
    if kode in dict(tab):
        return kode
    return "kendaraan" if "kendaraan" in dict(tab) else tab[0][0]


def _cari_kendaraan(qs, q):
    if q:
        qs = qs.filter(
            Q(nopol__icontains=q) | Q(merek__icontains=q) | Q(no_chasis__icontains=q) | Q(no_mesin__icontains=q)
        )
    return qs


class _Tautan(str):
    """A row's detail URL, carrying the URLs of its QR code modal and of its
    Hapus action (or '')."""
    hapus = ""
    qr = ""


def _laporan_per_kendaraan(request, judul, kendaraan, detail, nama_file, jenis, satuan=None, ekspor_qr=False, tab=None, pakai_satuan=True):
    """A report with one row per vehicle (``kendaraan``: in display order), a
    search field and no date filter; each row opens the ``detail`` modal.
    ``jenis``: the report's key in laporan_hapus.JENIS, for the Hapus action
    its rows get when the user may delete. ``satuan``: vehicle -> the unit
    for a Satuan column (none without it). ``ekspor_qr``: show the QR Code
    column and offer the QR codes as a Word document (Laporan Penambahan only).
    ``pakai_satuan``: show the Satuan filter."""
    from .laporan_hapus import boleh_hapus

    f = _filter(request)
    if ekspor_qr and request.GET.get("unduh") == "qr":
        from .laporan_qr import qr_word
        return qr_word(judul, kendaraan, nama_file.replace(".xlsx", ".docx").replace("laporan-", "qr-"))
    pakai_hapus = boleh_hapus(request.user)
    tautan = []
    for v in kendaraan:
        t = _Tautan(reverse(detail, args=[v.uuid]))
        t.qr = reverse("fleet:vehicle_qr_modal", args=[v.uuid])
        if pakai_hapus:
            t.hapus = reverse("accounts:laporan_hapus", args=[jenis, v.uuid])
        tautan.append(t)
    rows = [
        (v.nopol, v.merek, v.no_chasis or "-", v.no_mesin or "-", v.get_group_kendaraan_display())
        for v in kendaraan
    ]
    header = ["No. Registrasi", "Merk/Type", "No. Chasis", "No. Mesin", "Golongan"]
    if satuan is not None:
        header.append("Satuan")
        rows = [baris + (satuan(v) or "-",) for baris, v in zip(rows, kendaraan)]
    return _render(
        request, "accounts/laporan_tabel.html", judul, header, rows, f, nama_file,
        tautan=tautan, kolom_tanggal=0, kolom_utama=1, pakai_tanggal=False, pakai_cari=True,
        # Laporan Pemeriksaan, Perbaikan and Penambahan have no Excel download.
        pakai_excel=False, pakai_satuan=pakai_satuan, pakai_hapus=pakai_hapus, pakai_qr=ekspor_qr, pakai_ekspor_qr=ekspor_qr,
        tab=tab,
    )


def _kendaraan_dengan_catatan(request, model_dari_cfg, relasi_kendaraan, relasi_orang):
    """Vehicles with at least one record (inspection or repair) in the chosen
    group, by someone of the chosen Satuan (``relasi_orang``: the record's
    biodata), and matching the search, newest record first."""
    f = _filter(request)
    terakhir = {}  # vehicle id -> newest record time
    for _, cfg in _golongan_dipilih(f):
        qs = model_dari_cfg(cfg).objects.all()
        if f["satuan"]:
            qs = qs.filter(**{f"{relasi_orang}__satuan": f["satuan"]})
        qs = qs.order_by().values(relasi_kendaraan).annotate(waktu=Max("dibuat_pada"))
        for baris in qs:
            vid = baris[relasi_kendaraan]
            terakhir[vid] = max(baris["waktu"], terakhir.get(vid, baris["waktu"]))
    qs = _cari_kendaraan(Vehicle.objects.filter(pk__in=list(terakhir)), request.GET.get("q", "").strip())
    return sorted(qs, key=lambda v: (terakhir[v.pk], v.pk), reverse=True)


@login_required
def laporan_pemeriksaan(request):
    """One row per inspected vehicle; the row's modal lists the inspections."""
    kendaraan = _kendaraan_dengan_catatan(request, lambda cfg: cfg.pemeriksaan_model, "vehicle", "pemeriksa")
    return _laporan_per_kendaraan(
        request, "Laporan Pemeriksaan", kendaraan, "accounts:laporan_pemeriksaan_detail", "laporan-pemeriksaan.xlsx",
        "pemeriksaan", pakai_satuan=False,
    )


@login_required
def laporan_perbaikan(request):
    """One row per repaired vehicle; the row's modal lists the repairs."""
    kendaraan = _kendaraan_dengan_catatan(
        request, lambda cfg: cfg.perbaikan_model, "item__pemeriksaan__vehicle", "teknisi",
    )
    return _laporan_per_kendaraan(
        request, "Laporan Perbaikan", kendaraan, "accounts:laporan_perbaikan_detail", "laporan-perbaikan.xlsx",
        "perbaikan",
    )


@login_required
def laporan_penambahan(request):
    """Every vehicle, newest added first; the row's modal shows it and who added it."""
    f = _filter(request)
    qs = Vehicle.objects.select_related("penambah__satuan").order_by("-dibuat_pada", "-id")
    if f["golongan"]:
        qs = qs.filter(group_kendaraan=f["golongan"])
    if f["satuan"]:
        qs = qs.filter(penambah__satuan=f["satuan"])
    kendaraan = list(_cari_kendaraan(qs, request.GET.get("q", "").strip()))
    return _laporan_per_kendaraan(
        request, "Laporan Penambahan Kendaraan/Barang", kendaraan, "accounts:laporan_penambahan_detail",
        "laporan-penambahan-kendaraan.xlsx", "penambahan",
        # The unit of whoever added the vehicle (their biodata's Satuan).
        satuan=lambda v: v.penambah.satuan.nama if v.penambah and v.penambah.satuan else "",
        ekspor_qr=True,
    )


# Rekap Kerusakan: what a damaged part is listed as.
KONDISI_KERUSAKAN = [("RB", "Rusak Berat"), ("RR", "Rusak Ringan")]
_LENCANA_KERUSAKAN = {
    "RB": "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
    "RR": "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
}
# Rekap Kerusakan's Kondisi filter: what the part is now.
FILTER_KONDISI_REKAP = [*KONDISI_KERUSAKAN, ("B", "Baik")]
_LENCANA_BAIK = "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300"


@login_required
def rekap_kerusakan(request):
    """Rekap Kerusakan: every part its vehicle's last inspection found Rusak
    Ringan or Rusak Berat (or that a repair left so), one row per part,
    newest first, in the viewer's scope. Kondisi is what was found; once the
    part has been repaired it reads "found -> now" (Rusak Ringan -> Baik).
    Filtered by date, vehicle group (Jenis Kendaraan), Satuan, condition
    (what the part is now) and a search of the vehicle or the part; also as
    an Excel sheet and a PDF."""
    from django.utils.html import format_html, format_html_join
    from django.utils.safestring import mark_safe

    from . import dashboard

    f = _filter(request)
    kondisi = request.GET.get("kondisi", "")
    f["kondisi"] = kondisi if kondisi in dict(FILTER_KONDISI_REKAP) else ""
    q = request.GET.get("q", "").strip().lower()
    label = {**dict(KONDISI_KERUSAKAN), "B": "Baik", "ADA": "Ada", "TA": "Tidak Ada"}
    semua, _ = dashboard.komponen_rusak(
        dashboard.cakupan(request.user), tuple(dict(KONDISI_KERUSAKAN)),
        kodes=[f["golongan"]] if f["golongan"] else None, termasuk_selesai=True,
    )
    # The Kondisi filter looks at what the part is now: the condition after
    # the arrow for a repaired part (Baik: repaired to Baik).
    if f["kondisi"]:
        cocok = ("B", "ADA") if f["kondisi"] == "B" else (f["kondisi"],)
        semua = [b for b in semua if b["kondisi"] in cocok]
    rows, kode_kondisi = [], []
    for b in semua:
        v = b["vehicle"]
        satuan = v.penambah.satuan if v.penambah else None
        tanggal = timezone.localtime(b["waktu"]).date()
        if f["satuan"] and satuan != f["satuan"]:
            continue
        if (f["dari"] and tanggal < f["dari"]) or (f["sampai"] and tanggal > f["sampai"]):
            continue
        if q and not any(q in (teks or "").lower() for teks in (v.nopol, v.merek, v.no_chasis, v.no_mesin, b["item"].nama_alat)):
            continue
        oleh = b["perbaikan"].teknisi.nama if b["perbaikan"] else b["periksa"].pemeriksa.nama
        # Repaired: what was found and what it is now; not yet: the one condition.
        urutan = [b["awal"], b["kondisi"]] if b["perbaikan"] else [b["kondisi"]]
        kode_kondisi.append(urutan)
        rows.append((
            timezone.localtime(b["waktu"]).strftime("%d-%m-%Y %H:%M"), v.nopol, v.merek, v.get_group_kendaraan_display(),
            satuan.nama if satuan else "-", b["item"].nama_alat, " → ".join(label.get(k, k) for k in urutan),
            "Perbaikan" if b["perbaikan"] else "Pemeriksaan", oleh, b["keterangan"] or "-",
        ))
    header = [
        "Tanggal", "No. Registrasi", "Merk/Type", "Jenis Kendaraan", "Satuan", "Sparepart / Komponen",
        "Kondisi", "Sumber", "Oleh", "Keterangan",
    ]
    if request.GET.get("unduh") == "excel":
        return _excel("Rekap Kerusakan", header, rows, f, "rekap-kerusakan.xlsx")
    if request.GET.get("unduh") == "pdf":
        from . import laporan_pdf

        # The charts count what is still damaged; what was repaired to Baik is a number of its own.
        per_satuan, sudah_baik = {}, 0  # unit -> [Rusak Berat, Rusak Ringan]
        for baris, urutan in zip(rows, kode_kondisi):
            if urutan[-1] in ("RB", "RR"):
                per_satuan.setdefault(baris[4], [0, 0])[0 if urutan[-1] == "RB" else 1] += 1
            else:
                sudah_baik += 1
        keterangan = [_keterangan_filter(f).replace("Semua golongan", "Semua jenis kendaraan")]
        if f["kondisi"]:
            keterangan.append(f"Kondisi sekarang {label[f['kondisi']]}")
        if q:
            keterangan.append(f'cari "{request.GET.get("q", "").strip()}"')
        return laporan_pdf._pdf_response(request, laporan_pdf.buat_pdf_rekap_kerusakan(
            " · ".join(keterangan), [(nama, b, r) for nama, (b, r) in per_satuan.items()],
            header, [10, 22, 24, 24, 22, 34, 34, 34, 22, 18, 23], rows, sudah_baik=sudah_baik,
        ), "rekap-kerusakan.pdf")

    # On the page each condition is a coloured badge, an arrow between the two of a repaired part.
    def lencana(urutan):
        return format_html_join(
            mark_safe(' <span class="text-slate-400">→</span> '),  # a constant: nothing typed in it
            '<span class="rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap {}">{}</span>',
            ((_LENCANA_KERUSAKAN.get(k, _LENCANA_BAIK), label.get(k, k)) for k in urutan),
        )

    rows = [
        (*baris[:6], format_html('<span class="whitespace-nowrap">{}</span>', lencana(urutan)), *baris[7:])
        for baris, urutan in zip(rows, kode_kondisi)
    ]
    return _render(
        request, "accounts/laporan_tabel.html", "Rekap Kerusakan", header, rows, f, "rekap-kerusakan.xlsx",
        kolom_tanggal=1, kolom_utama=2, pakai_cari=True, pakai_satuan=True, kondisi_pilihan=FILTER_KONDISI_REKAP,
        pakai_pdf=True, per_halaman=10,
    )


JUDUL_RUSAK = "Laporan Rusak/Tidak Layak Pakai"
TAB_RUSAK = [("sparepart", "Sparepart"), ("kendaraan", "Kendaraan"), ("non_kendaraan", "Non Kendaraan")]


def _laporan_sparepart_rusak(request, f):
    """Laporan Rusak's Sparepart tab: every part that is Rusak Berat now
    (dashboard.sparepart_rusak), one row per part, newest first."""
    from . import dashboard

    q = request.GET.get("q", "").strip().lower()
    rows = []
    for b in dashboard.sparepart_rusak(None, batas=None)[0]:
        v = b["vehicle"]
        satuan = v.penambah.satuan if v.penambah else None
        if f["golongan"] and v.group_kendaraan != f["golongan"]:
            continue
        if f["satuan"] and satuan != f["satuan"]:
            continue
        if q and not any(q in (teks or "").lower() for teks in (v.nopol, v.merek, v.no_chasis, v.no_mesin, b["item"].nama_alat)):
            continue
        oleh = b["perbaikan"].teknisi.nama if b["perbaikan"] else b["periksa"].pemeriksa.nama
        rows.append((
            b["item"].nama_alat, v.nopol, v.merek, v.get_group_kendaraan_display(),
            satuan.nama if satuan else "-", "Perbaikan" if b["perbaikan"] else "Pemeriksaan",
            timezone.localtime(b["waktu"]).strftime("%d-%m-%Y %H:%M"), oleh, b["keterangan"] or "-",
        ))
    return _render(
        request, "accounts/laporan_tabel.html", JUDUL_RUSAK,
        ["Sparepart / Komponen", "No. Registrasi", "Merk/Type", "Golongan", "Satuan", "Sumber", "Tanggal", "Oleh", "Keterangan"],
        rows, f, "laporan-sparepart-rusak.xlsx", kolom_tanggal=7, kolom_utama=1, pakai_tanggal=False, pakai_cari=True,
        pakai_satuan=True, tab=TAB_RUSAK,
    )


@login_required
def laporan_rusak(request):
    """One row per vehicle declared Rusak/Tidak Layak Pakai (Form Rusak),
    newest declaration first; the row's modal lists its declarations."""
    from .models import KendaraanRusak

    f = _filter(request)
    tab = _tab(request, TAB_RUSAK)
    if tab == "sparepart":
        return _laporan_sparepart_rusak(request, f)
    if tab == "non_kendaraan":
        # Nothing to list yet: only vehicles can be declared rusak.
        return _laporan_per_kendaraan(
            request, JUDUL_RUSAK, [], "accounts:laporan_rusak_detail", "laporan-rusak.xlsx", "rusak",
            satuan=lambda v: "", tab=TAB_RUSAK,
        )
    qs = KendaraanRusak.objects.select_related("pelapor__satuan")
    if f["satuan"]:
        qs = qs.filter(pelapor__satuan=f["satuan"])
    terakhir = {}  # vehicle id -> its newest declaration
    for d in qs.order_by("dibuat_pada", "id"):
        terakhir[d.vehicle_id] = d
    kendaraan = Vehicle.objects.filter(pk__in=list(terakhir))
    if f["golongan"]:
        kendaraan = kendaraan.filter(group_kendaraan=f["golongan"])
    kendaraan = sorted(
        _cari_kendaraan(kendaraan, request.GET.get("q", "").strip()),
        key=lambda v: (terakhir[v.pk].dibuat_pada, v.pk), reverse=True,
    )
    return _laporan_per_kendaraan(
        request, JUDUL_RUSAK, kendaraan, "accounts:laporan_rusak_detail", "laporan-rusak.xlsx",
        "rusak", tab=TAB_RUSAK,
        # The unit of whoever declared it last (their biodata's Satuan).
        satuan=lambda v: terakhir[v.pk].pelapor.satuan.nama if terakhir[v.pk].pelapor.satuan else "",
    )


@login_required
def laporan_rusak_detail(request, uid):
    """Modal for a Laporan Rusak row: the vehicle's declarations (reason,
    photos) and the personnel who declared it."""
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    riwayat = list(vehicle.rusak.select_related("pelapor__satuan").order_by("-dibuat_pada", "-id"))
    return render(request, "accounts/_laporan_rusak_detail.html", {
        "vehicle": vehicle, "riwayat": riwayat, "personil": _per_orang(riwayat, "pelapor"),
    })


@login_required
def laporan_pemeriksaan_detail(request, uid):
    """Modal for a Laporan Pemeriksaan row: every inspection of that vehicle
    (the clicked one highlighted) and the personnel who inspected it."""
    vehicle = get_object_or_404(Vehicle, uuid=uid)
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
    """UUID of the row that was clicked (?<param>=<uuid>), or None."""
    try:
        return uuid.UUID(request.GET.get(param, ""))
    except ValueError:
        return None


@login_required
def laporan_perbaikan_detail(request, uid):
    """Modal for a Laporan Perbaikan row: every repair of that vehicle (the
    clicked one highlighted) and the personnel who repaired it."""
    vehicle = get_object_or_404(Vehicle, uuid=uid)
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
def laporan_penambahan_detail(request, uid):
    """Modal for a Laporan Penambahan row: the vehicle's data, photos and QR
    code, and who added it."""
    vehicle = get_object_or_404(
        Vehicle.objects.select_related("ditambahkan_oleh", "penambah__satuan").prefetch_related("fotos"), uuid=uid,
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

