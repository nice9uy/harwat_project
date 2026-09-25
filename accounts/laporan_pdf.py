"""Full PDF reports for the Laporan modals, one record each:

- an inspection: vehicle, inspection data, inspector, every checked part with
  its latest repair, a summary and a signature block;
- a repair: the part, its condition before and after, photos, the technician
  and the part's repair history;
- a vehicle added to the fleet: its data, photos, QR code and who added it.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import capfirst, slugify
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fleet.models import Vehicle
from fleet.qr import qr_png_with_logo

from . import golongan

NAVY = colors.HexColor("#0B1F3A")
GARIS = colors.HexColor("#CBD5E1")
ZEBRA = colors.HexColor("#F1F5F9")
WARNA_KONDISI = {
    "B": "#15803D", "ADA": "#0369A1", "RR": "#B45309", "HP": "#B45309",
    "RB": "#B91C1C", "HG": "#B91C1C", "TA": "#475569",
}
# Inspection fields shown elsewhere in the report (or not at all).
BUKAN_DATA = {"id", "pemeriksa", "vehicle", "dibuat_pada"}

_gaya = getSampleStyleSheet()
TEKS = ParagraphStyle("teks", parent=_gaya["Normal"], fontName="Helvetica", fontSize=8.5, leading=11)
TEKS_TEBAL = ParagraphStyle("teks_tebal", parent=TEKS, fontName="Helvetica-Bold")
KEPALA = ParagraphStyle("kepala", parent=TEKS, fontName="Helvetica-Bold", textColor=colors.white)
BAGIAN = ParagraphStyle("bagian", parent=TEKS, fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, spaceBefore=8, spaceAfter=4)
JUDUL = ParagraphStyle("judul", parent=TEKS, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY)
SUB = ParagraphStyle("sub", parent=TEKS, fontSize=9, textColor=colors.HexColor("#475569"))
TENGAH = ParagraphStyle("tengah", parent=TEKS, alignment=TA_CENTER)


def _p(nilai, gaya=TEKS):
    return Paragraph(escape(str(nilai if nilai not in (None, "") else "-")), gaya)


def _nilai(obj, field):
    if field.choices:
        return getattr(obj, f"get_{field.name}_display")()
    nilai = getattr(obj, field.name)
    if field.is_relation:
        return getattr(nilai, "nama", nilai)
    return nilai


def _data_pemeriksaan(hasil):
    """(label, value) for every inspection field, in model order."""
    return [
        (capfirst(f.verbose_name), _nilai(hasil, f))
        for f in hasil._meta.concrete_fields
        if f.name not in BUKAN_DATA
    ]


def _tabel_kunci_nilai(pasangan, kolom=2, total=180 * mm):
    """Label/value pairs laid out in ``kolom`` side-by-side columns, ``total`` wide."""
    baris = []
    per_kolom = -(-len(pasangan) // kolom)
    for i in range(per_kolom):
        sel = []
        for k in range(kolom):
            j = k * per_kolom + i
            if j < len(pasangan):
                sel += [_p(pasangan[j][0], TEKS_TEBAL), _p(pasangan[j][1])]
            else:
                sel += ["", ""]
        baris.append(sel)
    lebar = total / kolom
    tabel = Table(baris, colWidths=[lebar * 0.42, lebar * 0.58] * kolom)
    tabel.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GARIS),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabel


def _kondisi(kode, label):
    warna = WARNA_KONDISI.get(kode, "#0F172A")
    return Paragraph(f'<font color="{warna}"><b>{escape(kode)}</b></font> {escape(label)}', TEKS)


def _tabel_item(hasil, cfg):
    kepala = ["No", "Komponen"]
    if cfg.pakai_jumlah:
        kepala.append("Jumlah")
    if cfg.pakai_satuan:
        kepala += ["Sat", "Jml Riil", "Jml Nyata"]
    kepala += ["Kondisi", "Setelah Perbaikan", "Keterangan"]

    baris = [[Paragraph(k, KEPALA) for k in kepala]]
    for item in hasil.items.all():
        perbaikan = item.perbaikan.all()
        terakhir = perbaikan[0] if perbaikan else None
        sel = [_p(item.nomor, TENGAH), _p(item.nama_alat)]
        if cfg.pakai_jumlah:
            sel.append(_p(item.jumlah, TENGAH))
        if cfg.pakai_satuan:
            sel += [_p(item.satuan, TENGAH), _p(item.jumlah_riil, TENGAH), _p(item.jumlah_nyata, TENGAH)]
        sel += [
            _kondisi(item.kondisi, item.get_kondisi_display()),
            _kondisi(terakhir.kondisi, terakhir.get_kondisi_display()) if terakhir else _p("-", TENGAH),
            _p(item.keterangan),
        ]
        baris.append(sel)

    lebar_tetap = {"No": 9, "Jumlah": 16, "Sat": 12, "Jml Riil": 15, "Jml Nyata": 17, "Kondisi": 31, "Setelah Perbaikan": 31}
    sisa = 180 - sum(lebar_tetap.get(k, 0) for k in kepala)
    lentur = [k for k in kepala if k not in lebar_tetap]  # Komponen, Keterangan
    lebar = [lebar_tetap.get(k, sisa / len(lentur)) * mm for k in kepala]

    tabel = Table(baris, colWidths=lebar, repeatRows=1)
    gaya = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GARIS),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    gaya += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(baris), 2)]
    tabel.setStyle(TableStyle(gaya))
    return tabel


def _ringkasan(hasil, cfg):
    jumlah = {}
    for item in hasil.items.all():
        jumlah[item.kondisi] = jumlah.get(item.kondisi, 0) + 1
    pasangan = [(f"{kode} — {label}", jumlah.get(kode, 0)) for kode, label in cfg.kondisi]
    total = sum(jumlah.values())
    perlu = sum(n for kode, n in jumlah.items() if kode not in cfg.baik)
    pasangan += [("Jumlah item diperiksa", total), ("Item perlu perbaikan", perlu)]
    return _tabel_kunci_nilai(pasangan)


def _tanda_tangan(orang, peran, keterangan):
    """Signature block on the right: ``keterangan`` (e.g. the date), ``peran``, name, rank and NIP."""
    isi = [
        [_p(keterangan, TENGAH)],
        [_p(f"{peran},", TENGAH)],
        [Spacer(1, 14 * mm)],
        [Paragraph(f"<u><b>{escape(orang.nama)}</b></u>", TENGAH)],
        [_p(f"{orang.pangkat} · NIP {orang.nip}", TENGAH)],
    ]
    kotak = Table(isi, colWidths=[70 * mm])
    kotak.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    luar = Table([["", kotak]], colWidths=[110 * mm, 70 * mm])
    return KeepTogether([Spacer(1, 5 * mm), luar])


def _biodata(orang):
    return _tabel_kunci_nilai([
        ("NIP", orang.nip), ("Nama", orang.nama), ("Pangkat", orang.pangkat),
        ("Jabatan", orang.jabatan), ("Satuan", orang.satuan.nama),
    ])


def _data_kendaraan(vehicle, label_golongan, tambahan, total=180 * mm):
    return _tabel_kunci_nilai(total=total, pasangan=[
        ("No. Registrasi", vehicle.nopol), ("Merk/Type", vehicle.merek),
        ("No. Chasis", vehicle.no_chasis), ("No. Mesin", vehicle.no_mesin),
        ("Golongan", label_golongan), *tambahan,
    ])


def _gambar(berkas, lebar, tinggi_maks):
    """An uploaded image scaled to ``lebar`` (capped at ``tinggi_maks``), or None
    when it is missing or unreadable."""
    if not berkas:
        return None
    try:
        with berkas.open("rb") as f:
            data = BytesIO(f.read())
        w, h = ImageReader(data).getSize()
    except Exception:  # a file lost from storage must not break the whole report
        return None
    data.seek(0)
    skala = min(lebar / w, tinggi_maks / h)
    return Image(data, width=w * skala, height=h * skala)


def _galeri(gambar, per_baris=2):
    """Images (with captions) in a grid of ``per_baris`` columns."""
    lebar = 180 * mm / per_baris
    sel = []
    for berkas, judul in gambar:
        img = _gambar(berkas, lebar - 6 * mm, 65 * mm)
        if img is not None:
            sel.append([img, _p(judul, TENGAH)])
    if not sel:
        return _p("Tidak ada foto.")
    baris = [sel[i:i + per_baris] for i in range(0, len(sel), per_baris)]
    baris[-1] += [""] * (per_baris - len(baris[-1]))
    tabel = Table(baris, colWidths=[lebar] * per_baris)
    tabel.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tabel


def _kop(judul, label_golongan):
    logo = settings.BASE_DIR / "static" / "img" / "kemhan_logo.png"
    teks = [
        Paragraph("KEMENTERIAN PERTAHANAN REPUBLIK INDONESIA", SUB),
        Paragraph(escape(judul), JUDUL),
        Paragraph(escape(label_golongan), SUB),
    ]
    sel_logo = Image(str(logo), width=16 * mm, height=16 * mm) if logo.exists() else ""
    kop = Table([[sel_logo, teks]], colWidths=[20 * mm, 160 * mm])
    kop.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return kop


def _kaki(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(15 * mm, 10 * mm, f"BMN Harwat · dicetak {timezone.localtime():%d-%m-%Y %H:%M}")
    canvas.drawRightString(195 * mm, 10 * mm, f"Halaman {doc.page}")
    canvas.restoreState()


def _dokumen(isi, judul):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
        title=judul, author="BMN Harwat",
    )
    doc.build(isi, onFirstPage=_kaki, onLaterPages=_kaki)
    return buffer.getvalue()


def _tanggal(waktu):
    return f"{timezone.localtime(waktu):%d-%m-%Y %H:%M}" if waktu else "-"


def buat_pdf(hasil, cfg, label_golongan):
    """Inspection report. ``label_golongan``: the group whose form was filled
    in (the vehicle's group may have changed since)."""
    vehicle = hasil.vehicle
    isi = [
        _kop("LAPORAN PEMERIKSAAN KENDARAAN", label_golongan),
        Paragraph("Data Kendaraan", BAGIAN),
        _data_kendaraan(vehicle, label_golongan, [("Tanggal Pemeriksaan", _tanggal(hasil.dibuat_pada))]),
        Paragraph("Data Pemeriksaan", BAGIAN),
        _tabel_kunci_nilai(_data_pemeriksaan(hasil)),
        Paragraph("Personil yang Memeriksa", BAGIAN),
        _biodata(hasil.pemeriksa),
        Paragraph("Hasil Pemeriksaan", BAGIAN),
        _tabel_item(hasil, cfg),
        Paragraph("Ringkasan", BAGIAN),
        _ringkasan(hasil, cfg),
        _tanda_tangan(hasil.pemeriksa, "Pemeriksa", f"Diperiksa pada {timezone.localtime(hasil.dibuat_pada):%d-%m-%Y}"),
    ]
    return _dokumen(isi, f"Laporan Pemeriksaan {vehicle.nopol}")


def _tabel_riwayat_perbaikan(daftar, dipilih):
    kepala = ["No", "Tanggal", "Kondisi Setelah", "Teknisi", "Keterangan"]
    baris = [[Paragraph(k, KEPALA) for k in kepala]]
    for nomor, p in enumerate(daftar, start=1):
        baris.append([
            _p(nomor, TENGAH), _p(_tanggal(p.dibuat_pada)), _kondisi(p.kondisi, p.get_kondisi_display()),
            _p(f"{p.teknisi.nama} ({p.teknisi.pangkat})"), _p(p.keterangan),
        ])
    tabel = Table(baris, colWidths=[9 * mm, 28 * mm, 31 * mm, 45 * mm, 67 * mm], repeatRows=1)
    gaya = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GARIS),
    ]
    gaya += [
        ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF3C7"))
        for i, p in enumerate(daftar, start=1) if p.pk == dipilih.pk
    ]
    tabel.setStyle(TableStyle(gaya))
    return tabel


def buat_pdf_perbaikan(perbaikan, label_golongan):
    item = perbaikan.item
    hasil = item.pemeriksaan
    data = [
        ("Komponen", f"{item.nomor}. {item.nama_alat}"),
        ("Tanggal Pemeriksaan", _tanggal(hasil.dibuat_pada)),
        ("Kondisi Saat Diperiksa", item.get_kondisi_display()),
        ("Pemeriksa", f"{hasil.pemeriksa.nama} ({hasil.pemeriksa.pangkat})"),
        ("Keterangan Pemeriksaan", item.keterangan),
        ("Tanggal Perbaikan", _tanggal(perbaikan.dibuat_pada)),
        ("Kondisi Setelah Perbaikan", perbaikan.get_kondisi_display()),
    ]
    if hasattr(perbaikan, "jumlah"):
        data.append(("Jumlah", perbaikan.jumlah))
    data.append(("Keterangan Perbaikan", perbaikan.keterangan))
    isi = [
        _kop("LAPORAN PERBAIKAN KENDARAAN", label_golongan),
        Paragraph("Data Kendaraan", BAGIAN),
        _data_kendaraan(hasil.vehicle, label_golongan, [("Tanggal Perbaikan", _tanggal(perbaikan.dibuat_pada))]),
        Paragraph("Data Perbaikan", BAGIAN),
        _tabel_kunci_nilai(data, kolom=1),
        Paragraph("Foto", BAGIAN),
        _galeri([(item.foto, "Saat diperiksa"), (perbaikan.foto, "Setelah perbaikan")]),
        Paragraph("Personil yang Memperbaiki", BAGIAN),
        _biodata(perbaikan.teknisi),
        Paragraph("Riwayat Perbaikan Komponen Ini", BAGIAN),
        _tabel_riwayat_perbaikan(list(item.perbaikan.all()), perbaikan),
        _tanda_tangan(perbaikan.teknisi, "Teknisi", f"Diperbaiki pada {timezone.localtime(perbaikan.dibuat_pada):%d-%m-%Y}"),
    ]
    return _dokumen(isi, f"Laporan Perbaikan {hasil.vehicle.nopol}")


def buat_pdf_penambahan(vehicle):
    label = vehicle.get_group_kendaraan_display()
    akun = vehicle.ditambahkan_oleh
    qr = Image(BytesIO(qr_png_with_logo(vehicle.qr_text())), width=40 * mm, height=40 * mm)
    data = _data_kendaraan(vehicle, label, [
        ("Ditambahkan Pada", _tanggal(vehicle.dibuat_pada)),
        ("Akun Penambah", (akun.get_full_name() or akun.username) if akun else "-"),
    ], total=135 * mm)  # leaves room for the QR code
    atas = Table([[data, qr]], colWidths=[135 * mm, 45 * mm])
    atas.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    isi = [
        _kop("LAPORAN PENAMBAHAN KENDARAAN/BARANG", label),
        Paragraph("Data Kendaraan/Barang", BAGIAN),
        atas,
        Paragraph("Foto Kendaraan/Barang", BAGIAN),
        _galeri([(f.image, f"Foto {i}") for i, f in enumerate(vehicle.fotos.all(), start=1)]),
        Paragraph("Personil yang Menambahkan", BAGIAN),
        _biodata(vehicle.penambah) if vehicle.penambah else _p(
            "Belum tercatat: kendaraan ini ditambahkan sebelum biodata penambah disimpan, atau lewat menu Armada."
        ),
    ]
    if vehicle.penambah:
        tanggal = f"Ditambahkan pada {timezone.localtime(vehicle.dibuat_pada):%d-%m-%Y}" if vehicle.dibuat_pada else ""
        isi.append(_tanda_tangan(vehicle.penambah, "Penambah", tanggal))
    return _dokumen(isi, f"Laporan Penambahan {vehicle.nopol}")


def _pdf_response(request, konten, nama_file):
    response = HttpResponse(konten, content_type="application/pdf")
    disposisi = "attachment" if request.GET.get("unduh") else "inline"
    response["Content-Disposition"] = f'{disposisi}; filename="{nama_file}"'
    return response


@login_required
def laporan_pemeriksaan_pdf(request, kode, pk):
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404
    hasil = get_object_or_404(
        cfg.pemeriksaan_model.objects.select_related("vehicle", "pemeriksa__satuan").prefetch_related(
            "items__perbaikan",
        ),
        pk=pk,
    )
    lokal = timezone.localtime(hasil.dibuat_pada)
    nama_file = f"laporan-pemeriksaan-{slugify(hasil.vehicle.nopol)}-{lokal:%Y%m%d-%H%M}.pdf"
    return _pdf_response(request, buat_pdf(hasil, cfg, Vehicle.GroupKendaraan(kode).label), nama_file)


@login_required
def laporan_perbaikan_pdf(request, kode, pk):
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404
    perbaikan = get_object_or_404(
        cfg.perbaikan_model.objects.select_related(
            "teknisi__satuan", "item__pemeriksaan__vehicle", "item__pemeriksaan__pemeriksa",
        ).prefetch_related("item__perbaikan__teknisi"),
        pk=pk,
    )
    lokal = timezone.localtime(perbaikan.dibuat_pada)
    nama_file = f"laporan-perbaikan-{slugify(perbaikan.item.pemeriksaan.vehicle.nopol)}-{lokal:%Y%m%d-%H%M}.pdf"
    return _pdf_response(request, buat_pdf_perbaikan(perbaikan, Vehicle.GroupKendaraan(kode).label), nama_file)


@login_required
def laporan_penambahan_pdf(request, pk):
    vehicle = get_object_or_404(
        Vehicle.objects.select_related("ditambahkan_oleh", "penambah__satuan").prefetch_related("fotos"), pk=pk,
    )
    nama_file = f"laporan-penambahan-{slugify(vehicle.nopol)}.pdf"
    return _pdf_response(request, buat_pdf_penambahan(vehicle), nama_file)
