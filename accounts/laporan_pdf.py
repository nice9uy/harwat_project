"""Full report of one inspection as a PDF: vehicle, inspection data,
inspector, every checked part with its latest repair, and a signature block."""
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
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from fleet.models import Vehicle

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


def _tabel_kunci_nilai(pasangan, kolom=2):
    """Label/value pairs laid out in ``kolom`` side-by-side columns."""
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
    lebar = (180 * mm) / kolom
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


def _tanda_tangan(hasil):
    p = hasil.pemeriksa
    lokal = timezone.localtime(hasil.dibuat_pada)
    isi = [
        [_p(f"Diperiksa pada {lokal:%d-%m-%Y}", TENGAH)],
        [_p("Pemeriksa,", TENGAH)],
        [Spacer(1, 14 * mm)],
        [Paragraph(f"<u><b>{escape(p.nama)}</b></u>", TENGAH)],
        [_p(f"{p.pangkat} · NIP {p.nip}", TENGAH)],
    ]
    kotak = Table(isi, colWidths=[70 * mm])
    kotak.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    luar = Table([["", kotak]], colWidths=[110 * mm, 70 * mm])
    return KeepTogether([Spacer(1, 5 * mm), luar])


def _kop(label_golongan):
    logo = settings.BASE_DIR / "static" / "img" / "kemhan_logo.png"
    teks = [
        Paragraph("KEMENTERIAN PERTAHANAN REPUBLIK INDONESIA", SUB),
        Paragraph("LAPORAN PEMERIKSAAN KENDARAAN", JUDUL),
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


def buat_pdf(hasil, cfg, label_golongan):
    """``label_golongan``: the group whose form was filled in (the vehicle's
    group may have changed since)."""
    vehicle = hasil.vehicle
    p = hasil.pemeriksa
    lokal = timezone.localtime(hasil.dibuat_pada)
    isi = [
        _kop(label_golongan),
        Paragraph("Data Kendaraan", BAGIAN),
        _tabel_kunci_nilai([
            ("No. Registrasi", vehicle.nopol), ("Merk/Type", vehicle.merek),
            ("No. Chasis", vehicle.no_chasis), ("No. Mesin", vehicle.no_mesin),
            ("Golongan", label_golongan), ("Tanggal Pemeriksaan", f"{lokal:%d-%m-%Y %H:%M}"),
        ]),
        Paragraph("Data Pemeriksaan", BAGIAN),
        _tabel_kunci_nilai(_data_pemeriksaan(hasil)),
        Paragraph("Personil yang Memeriksa", BAGIAN),
        _tabel_kunci_nilai([
            ("NIP", p.nip), ("Nama", p.nama), ("Pangkat", p.pangkat),
            ("Jabatan", p.jabatan), ("Satuan", p.satuan.nama),
        ]),
        Paragraph("Hasil Pemeriksaan", BAGIAN),
        _tabel_item(hasil, cfg),
        Paragraph("Ringkasan", BAGIAN),
        _ringkasan(hasil, cfg),
        _tanda_tangan(hasil),
    ]
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
        title=f"Laporan Pemeriksaan {vehicle.nopol}", author="BMN Harwat",
    )
    doc.build(isi, onFirstPage=_kaki, onLaterPages=_kaki)
    return buffer.getvalue()


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
    label = Vehicle.GroupKendaraan(kode).label
    response = HttpResponse(buat_pdf(hasil, cfg, label), content_type="application/pdf")
    disposisi = "attachment" if request.GET.get("unduh") else "inline"
    response["Content-Disposition"] = f'{disposisi}; filename="{nama_file}"'
    return response

