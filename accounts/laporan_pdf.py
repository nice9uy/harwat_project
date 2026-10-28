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
from reportlab.lib.pagesizes import A4, landscape
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
SUBKEPALA = colors.HexColor("#DBE4F0")
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
KEPALA_KECIL = ParagraphStyle("kepala_kecil", parent=KEPALA, fontSize=7.5, leading=9.5)
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
    kepala += ["Kondisi", "Keterangan"]

    baris = [[Paragraph(k, KEPALA) for k in kepala]]
    for item in hasil.items.all():
        sel = [_p(item.nomor, TENGAH), _p(item.nama_alat)]
        if cfg.pakai_jumlah:
            sel.append(_p(item.jumlah, TENGAH))
        if cfg.pakai_satuan:
            sel += [_p(item.satuan, TENGAH), _p(item.jumlah_riil, TENGAH), _p(item.jumlah_nyata, TENGAH)]
        sel += [_kondisi(item.kondisi, item.get_kondisi_display()), _p(item.keterangan)]
        baris.append(sel)

    lebar_tetap = {"No": 9, "Jumlah": 16, "Sat": 12, "Jml Riil": 15, "Jml Nyata": 17, "Kondisi": 31}
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
    """Signature block on the right: ``keterangan`` (e.g. the date), the
    signer's jabatan (``peran`` when their biodata has none), name, rank and NIP."""
    isi = [[_p(keterangan, TENGAH)]] if keterangan else []
    isi += [
        [_p(f"{getattr(orang, 'jabatan', '') or peran},", TENGAH)],
        [Spacer(1, 14 * mm)],
        [_p(orang.nama, TENGAH)],
    ]
    # A signer without biodata (a bare account) has just the name.
    if getattr(orang, "nip", ""):
        isi.append([_p(f"{orang.pangkat} · {orang.label_nip} {orang.nip}", TENGAH)])
    kotak = Table(isi, colWidths=[70 * mm])
    kotak.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    luar = Table([["", kotak]], colWidths=[110 * mm, 70 * mm])
    return KeepTogether([Spacer(1, 5 * mm), luar])


def _biodata(orang):
    return _tabel_kunci_nilai([
        (orang.label_nip, orang.nip), ("Nama", orang.nama), ("Pangkat", orang.pangkat),
        ("Jabatan", orang.jabatan), ("Satuan", orang.satuan.nama),
    ])


def _data_kendaraan(vehicle, label_golongan, tambahan):
    return _tabel_kunci_nilai([
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


def _galeri(gambar, per_baris=2, tinggi_maks=65 * mm):
    """Images (with captions) in a grid of ``per_baris`` columns, each at most ``tinggi_maks`` tall."""
    lebar = 180 * mm / per_baris
    sel = []
    for berkas, judul in gambar:
        img = _gambar(berkas, lebar - 6 * mm, tinggi_maks)
        if img is not None:
            sel.append([img, _p(judul, TENGAH)])
    if not sel:
        return _p("Tidak ada foto.")
    baris = [sel[i:i + per_baris] for i in range(0, len(sel), per_baris)]
    baris[-1] += [""] * (per_baris - len(baris[-1]))
    tabel = Table(baris, colWidths=[lebar] * per_baris)
    tabel.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tabel


def _teks_qr(judul, bagian):
    """QR content: the report title, then each section's "label: value" lines."""
    baris = [judul]
    for nama, pasangan in bagian:
        baris.append(f"[{nama}]")
        baris += [f"{label}: {nilai if nilai not in (None, '') else '-'}" for label, nilai in pasangan]
    return "\n".join(baris)


def _data_kendaraan_qr(vehicle, label_golongan):
    return ("Kendaraan", [
        ("No. Registrasi", vehicle.nopol), ("Merk/Type", vehicle.merek), ("No. Chasis", vehicle.no_chasis),
        ("No. Mesin", vehicle.no_mesin), ("Golongan", label_golongan),
    ])


def _personil_qr(nama_bagian, orang):
    return (nama_bagian, [
        (orang.label_nip, orang.nip), ("Nama", orang.nama), ("Pangkat", orang.pangkat),
        ("Jabatan", orang.jabatan), ("Satuan", orang.satuan.nama),
    ])


def _kop(judul, label_golongan, qr_teks=None, lebar=180 * mm):
    """Letterhead; with ``qr_teks`` a QR code of the report's key data sits on the right."""
    logo = settings.BASE_DIR / "static" / "img" / "kemhan_logo.png"
    teks = [
        Paragraph("KEMENTERIAN PERTAHANAN REPUBLIK INDONESIA", SUB),
        Paragraph(escape(judul), JUDUL),
        Paragraph(escape(label_golongan), SUB),
    ]
    sel_logo = Image(str(logo), width=16 * mm, height=16 * mm) if logo.exists() else ""
    # Logo in the middle (error level H): printed large enough that this much
    # text stays scannable.
    sel_qr = Image(BytesIO(qr_png_with_logo(qr_teks)), width=36 * mm, height=36 * mm) if qr_teks else ""
    kop = Table([[sel_logo, teks, sel_qr]], colWidths=[20 * mm, lebar - 58 * mm, 38 * mm])
    kop.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return kop


def _kaki(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(15 * mm, 10 * mm, f"Pemeliharaan dan Perawatan · dicetak {timezone.localtime():%d-%m-%Y %H:%M}")
    canvas.drawRightString(doc.pagesize[0] - 15 * mm, 10 * mm, f"Halaman {doc.page}")
    canvas.restoreState()


def _dokumen(isi, judul, mendatar=False):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4) if mendatar else A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=16 * mm,
        title=judul, author="Pemeliharaan dan Perawatan",
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
        _kop("LAPORAN PEMERIKSAAN KENDARAAN", label_golongan, _teks_qr("Laporan Pemeriksaan Kendaraan", [
            _data_kendaraan_qr(vehicle, label_golongan),
            ("Pemeriksaan", [("Tanggal", _tanggal(hasil.dibuat_pada))]),
            _personil_qr("Personil yang Memeriksa", hasil.pemeriksa),
        ])),
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
        _kop("LAPORAN PERBAIKAN KENDARAAN", label_golongan, _teks_qr("Laporan Perbaikan Kendaraan", [
            _data_kendaraan_qr(hasil.vehicle, label_golongan),
            ("Perbaikan", [
                ("Komponen", f"{item.nomor}. {item.nama_alat}"), ("Tanggal", _tanggal(perbaikan.dibuat_pada)),
                ("Kondisi", f"{item.get_kondisi_display()} -> {perbaikan.get_kondisi_display()}"),
            ]),
            _personil_qr("Personil yang Memperbaiki", perbaikan.teknisi),
        ])),
        Paragraph("Data Kendaraan", BAGIAN),
        _data_kendaraan(hasil.vehicle, label_golongan, [("Tanggal Perbaikan", _tanggal(perbaikan.dibuat_pada))]),
        Paragraph("Data Perbaikan", BAGIAN),
        _tabel_kunci_nilai(data, kolom=1),
        Paragraph("Foto", BAGIAN),
        _galeri(
            [(f, f"Saat diperiksa {i}") for i, f in enumerate(item.daftar_foto, start=1)]
            + [(f, f"Setelah perbaikan {i}") for i, f in enumerate(perbaikan.daftar_foto, start=1)]
        ),
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
    # The letterhead's QR code carries the vehicle (and adder) data.
    data = _data_kendaraan(vehicle, label, [
        ("Ditambahkan Pada", _tanggal(vehicle.dibuat_pada)),
        ("Akun Penambah", (akun.get_full_name() or akun.username) if akun else "-"),
    ])
    isi = [
        _kop("LAPORAN PENAMBAHAN KENDARAAN/BARANG", label, _teks_qr("Laporan Penambahan Kendaraan/Barang", [
            _data_kendaraan_qr(vehicle, label),
            ("Penambahan", [("Tanggal", _tanggal(vehicle.dibuat_pada))]),
            *([_personil_qr("Personil yang Menambahkan", vehicle.penambah)] if vehicle.penambah else []),
        ])),
        Paragraph("Data Kendaraan/Barang", BAGIAN),
        data,
        Paragraph("Foto Kendaraan/Barang", BAGIAN),
        # One row of four small photos keeps the report on a single page.
        _galeri([(f.image, f"Foto {i}") for i, f in enumerate(vehicle.fotos.all(), start=1)], 4, 45 * mm),
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
def laporan_pemeriksaan_pdf(request, kode, uid):
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404
    hasil = get_object_or_404(
        cfg.pemeriksaan_model.objects.select_related("vehicle", "pemeriksa__satuan").prefetch_related(
            "items__perbaikan",
        ),
        uuid=uid,
    )
    lokal = timezone.localtime(hasil.dibuat_pada)
    nama_file = f"laporan-pemeriksaan-{slugify(hasil.vehicle.nopol)}-{lokal:%Y%m%d-%H%M}.pdf"
    return _pdf_response(request, buat_pdf(hasil, cfg, Vehicle.GroupKendaraan(kode).label), nama_file)


@login_required
def laporan_perbaikan_pdf(request, kode, uid):
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404
    perbaikan = get_object_or_404(
        cfg.perbaikan_model.objects.select_related(
            "teknisi__satuan", "item__pemeriksaan__vehicle", "item__pemeriksaan__pemeriksa",
        ).prefetch_related("item__perbaikan__teknisi"),
        uuid=uid,
    )
    lokal = timezone.localtime(perbaikan.dibuat_pada)
    nama_file = f"laporan-perbaikan-{slugify(perbaikan.item.pemeriksaan.vehicle.nopol)}-{lokal:%Y%m%d-%H%M}.pdf"
    return _pdf_response(request, buat_pdf_perbaikan(perbaikan, Vehicle.GroupKendaraan(kode).label), nama_file)


@login_required
def laporan_penambahan_pdf(request, uid):
    vehicle = get_object_or_404(
        Vehicle.objects.select_related("ditambahkan_oleh", "penambah__satuan").prefetch_related("fotos"), uuid=uid,
    )
    nama_file = f"laporan-penambahan-{slugify(vehicle.nopol)}.pdf"
    return _pdf_response(request, buat_pdf_penambahan(vehicle), nama_file)


def _tabel_data(kepala, lebar_mm, baris_data):
    """A navy-headed, zebra-striped table; ``lebar_mm`` per column."""
    baris = [[Paragraph(k, KEPALA_KECIL) for k in kepala]] + [[_p(sel) for sel in b] for b in baris_data]
    if not baris_data:
        baris.append([_p("Tidak ada data.", TENGAH)] + [""] * (len(kepala) - 1))
    tabel = Table(baris, colWidths=[w * mm for w in lebar_mm], repeatRows=1)
    gaya = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GARIS),
    ]
    gaya += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(baris), 2)]
    if not baris_data:
        gaya.append(("SPAN", (0, 1), (-1, 1)))
    tabel.setStyle(TableStyle(gaya))
    return tabel


# Rekap Kerusakan's chart: the status colours of a damaged part, each always
# beside its label and its count (never colour alone).
WARNA_KERUSAKAN = {"RB": colors.HexColor("#D03B3B"), "RR": colors.HexColor("#FAB219")}
# The per-unit pie: this many units as slices (the app's pie colours), the
# rest summed up in one grey slice, so the slices stay tellable apart.
SATUAN_PIE_PDF = 7
WARNA_SATUAN_PIE = [colors.HexColor(h) for h in ("#2A78D6", "#EB6834", "#12996B", "#C98A00", "#8250DF", "#D6336C", "#0B8FA8")]
WARNA_LAINNYA_PIE = colors.HexColor("#7B8794")


def _pie(d, cx, cy, r, bagian):
    """Draws [(n, colour)] as a pie on ``d``, clockwise from 12 o'clock, a
    hair of the page between slices; a ring when there is nothing to show."""
    from reportlab.graphics.shapes import Circle, Wedge

    bagian = [(n, warna) for n, warna in bagian if n]
    total = sum(n for n, _ in bagian)
    if not total:
        d.add(Circle(cx, cy, r, fillColor=None, strokeColor=GARIS, strokeWidth=4))
        return
    if len(bagian) == 1:
        d.add(Circle(cx, cy, r, fillColor=bagian[0][1], strokeColor=None))
        return
    sudut = 90.0
    for n, warna in bagian:
        lebar = 360.0 * n / total
        d.add(Wedge(cx, cy, r, sudut - lebar, sudut, fillColor=warna, strokeColor=colors.white, strokeWidth=1.2))
        sudut -= lebar


def _grafik_kerusakan_per_satuan(per_satuan, lebar=267 * mm):
    """Two pies side by side: the damaged parts by condition (Rusak Berat,
    Rusak Ringan), and by unit (the SATUAN_PIE_PDF biggest, then "Lainnya"),
    each with a legend giving the count and share, and per unit its split.
    ``per_satuan``: [(unit, n Rusak Berat, n Rusak Ringan)]."""
    from reportlab.graphics.shapes import Drawing, Rect, String

    data = sorted(per_satuan, key=lambda s: (-(s[1] + s[2]), s[0]))
    if len(data) > SATUAN_PIE_PDF:
        sisa = data[SATUAN_PIE_PDF:]
        data = data[:SATUAN_PIE_PDF] + [
            (f"Lainnya ({len(sisa)} satuan)", sum(s[1] for s in sisa), sum(s[2] for s in sisa))
        ]
    berat, ringan = sum(s[1] for s in data), sum(s[2] for s in data)
    total = berat + ringan
    tinggi, r = 68 * mm, 24 * mm
    d = Drawing(lebar, tinggi)
    tinta, redup = colors.HexColor("#1E293B"), colors.HexColor("#64748B")
    cy = tinggi - 8 * mm - r

    def persen(n):
        return f"{100 * n / total:.1f}%".replace(".", ",") if total else "0%"

    def judul(x, teks):
        d.add(String(x, tinggi - 4 * mm, teks, fontName="Helvetica-Bold", fontSize=8.5, fillColor=tinta))

    def baris_legenda(x, y, warna, label, n, tambahan="", lebar_label=44 * mm):
        d.add(Rect(x, y - 0.3 * mm, 3 * mm, 3 * mm, rx=1, ry=1, fillColor=warna, strokeColor=None))
        d.add(String(x + 4.5 * mm, y, label, fontName="Helvetica", fontSize=8, fillColor=tinta))
        d.add(String(x + lebar_label + 13 * mm, y, str(n), fontName="Helvetica-Bold", fontSize=8, fillColor=tinta, textAnchor="end"))
        d.add(String(x + lebar_label + 26 * mm, y, persen(n), fontName="Helvetica", fontSize=8, fillColor=redup, textAnchor="end"))
        if tambahan:
            d.add(String(x + lebar_label + 28 * mm, y, tambahan, fontName="Helvetica", fontSize=7, fillColor=redup))

    # Left: by condition.
    judul(0, "Menurut Kondisi")
    _pie(d, r, cy, r, [(berat, WARNA_KERUSAKAN["RB"]), (ringan, WARNA_KERUSAKAN["RR"])])
    x = 2 * r + 6 * mm
    baris_legenda(x, cy + 3 * mm, WARNA_KERUSAKAN["RB"], "Rusak Berat", berat, lebar_label=19 * mm)
    baris_legenda(x, cy - 4 * mm, WARNA_KERUSAKAN["RR"], "Rusak Ringan", ringan, lebar_label=19 * mm)

    # Right: by unit.
    x_pie = 132 * mm
    judul(x_pie - r, "Menurut Satuan")
    warna = [
        WARNA_LAINNYA_PIE if nama.startswith("Lainnya (") else WARNA_SATUAN_PIE[i % len(WARNA_SATUAN_PIE)]
        for i, (nama, _, _) in enumerate(data)
    ]
    _pie(d, x_pie, cy, r, [(b + rg, w) for (_, b, rg), w in zip(data, warna)])
    x = x_pie + r + 6 * mm
    if not data:
        d.add(String(x, cy, "Tidak ada data.", fontName="Helvetica", fontSize=8, fillColor=redup))
    y = cy + (len(data) - 1) * 3.4 * mm
    for (nama, b, rg), w in zip(data, warna):
        label = nama if len(nama) <= 24 else nama[:23] + "…"
        rinci = " · ".join(filter(None, [f"{b} berat" if b else "", f"{rg} ringan" if rg else ""]))
        baris_legenda(x, y, w, label, b + rg, f"({rinci})")
        y -= 6.8 * mm
    return d


def buat_pdf_rekap_kerusakan(keterangan, per_satuan, kepala, lebar_mm, baris_data, sudah_baik=0):
    """Rekap Kerusakan as a landscape PDF: the totals, the pies of the parts
    still damaged (by condition, by unit), and under them the detail table
    (with a No column). ``sudah_baik``: the parts repaired to Baik since,
    listed in the table but not in the pies."""
    berat = sum(s[1] for s in per_satuan)
    ringan = sum(s[2] for s in per_satuan)
    return _dokumen([
        _kop("REKAP KERUSAKAN", keterangan, lebar=267 * mm),
        Spacer(1, 3 * mm),
        _tabel_data(
            ["Masih Rusak", "Rusak Berat", "Rusak Ringan", "Sudah Diperbaiki (Baik)", "Satuan Terdampak"], [53.4] * 5,
            [[berat + ringan, berat, ringan, sudah_baik, len(per_satuan)]],
        ),
        Paragraph("Kerusakan yang Masih Ada", BAGIAN),
        _grafik_kerusakan_per_satuan(per_satuan),
        # Kept with the table's first rows, not left alone at the foot of a page.
        Paragraph("Rincian Kerusakan", ParagraphStyle("bagian_ikut", parent=BAGIAN, keepWithNext=1)),
        _tabel_data(["No", *kepala], lebar_mm, [[n, *b] for n, b in enumerate(baris_data, start=1)]),
        Spacer(1, 2 * mm),
        Paragraph(f"Jumlah: {len(baris_data)} data", SUB),
    ], "Rekap Kerusakan", mendatar=True)


def buat_pdf_tabel(judul, keterangan, kepala, baris_data):
    """A report's table as it is filtered on its page, as a landscape PDF:
    letterhead, the table (with a No column, the other columns sharing the
    width) and the row count."""
    lebar = 267
    kolom = [10] + [(lebar - 10) / len(kepala)] * len(kepala)
    return _dokumen([
        _kop(judul.upper(), keterangan, lebar=lebar * mm),
        Spacer(1, 4 * mm),
        _tabel_data(["No", *kepala], kolom, [[n, *b] for n, b in enumerate(baris_data, start=1)]),
        Spacer(1, 2 * mm),
        Paragraph(f"Jumlah: {len(baris_data)} data", SUB),
    ], judul, mendatar=True)


def _tabel_kelompok(kepala, lebar_mm, kelompok):
    """Like _tabel_data, with the rows in groups: ``kelompok`` is a list of
    (label, rows), each group under a full-width row naming it."""
    baris = [[Paragraph(k, KEPALA_KECIL) for k in kepala]]
    judul = []
    for label, isi in kelompok:
        judul.append(len(baris))
        baris.append([_p(f"{label} ({len(isi)})", TEKS_TEBAL)] + [""] * (len(kepala) - 1))
        baris += [[_p(sel) for sel in b] for b in isi]
    if not kelompok:
        baris.append([_p("Tidak ada data.", TENGAH)] + [""] * (len(kepala) - 1))
    tabel = Table(baris, colWidths=[w * mm for w in lebar_mm], repeatRows=1)
    gaya = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, GARIS),
    ]
    for i in judul or [1]:
        gaya.append(("SPAN", (0, i), (-1, i)))
    gaya += [("BACKGROUND", (0, i), (-1, i), SUBKEPALA) for i in judul]
    tabel.setStyle(TableStyle(gaya))
    return tabel


def _per_golongan(aktivitas):
    """Activities as [(golongan label, rows)], groups in the order of
    Vehicle.GroupKendaraan, rows keeping their order (newest first)."""
    urutan = {label: i for i, label in enumerate(Vehicle.GroupKendaraan.labels)}
    kelompok = {}
    for a in aktivitas:
        kelompok.setdefault(a["golongan"] or "-", []).append(a)
    return sorted(kelompok.items(), key=lambda kv: urutan.get(kv[0], len(urutan)))


def buat_pdf_tim(k):
    """Team report from laporan_tim.konteks_tim()."""
    ketua = k["ketua"]
    kb = k["ketua_baris"]
    nama_ketua = kb.nama or ketua.get_full_name() or ketua.username
    isi = [
        _kop("LAPORAN TIM", k["keterangan_filter"], _teks_qr("Laporan Tim", [
            ("Tim", [
                ("Ketua Tim", nama_ketua), ("Periode", k["keterangan_filter"]),
                ("Pemeriksaan", k["total"]["pemeriksaan"]), ("Perbaikan", k["total"]["perbaikan"]),
                ("Penambahan Kendaraan", k["total"]["penambahan"]),
            ]),
            ("Personil", [(u.keanggotaan, u.nama or u.get_full_name() or u.username) for u in k["anggota"]]),
        ])),
        Paragraph("Ringkasan", BAGIAN),
        _tabel_data(
            ["Ketua Tim", "Jumlah Anggota", "Pemeriksaan", "Perbaikan", "Penambahan Kendaraan", "Total Kegiatan"],
            [44, 26, 26, 24, 34, 26],
            [(
                nama_ketua, k["jumlah_anggota"], k["total"]["pemeriksaan"], k["total"]["perbaikan"],
                k["total"]["penambahan"], sum(k["total"].values()),
            )],
        ),
        Paragraph("Ketua Tim", BAGIAN),
        _tabel_data(
            ["Username", "Nama", kb.label_nip, "Pangkat", "Jabatan"],
            [30, 48, 34, 30, 38],
            [(kb.username, nama_ketua, kb.nip, kb.pangkat, kb.jabatan)],
        ),
        Paragraph("Anggota Tim", BAGIAN),
        _tabel_data(
            ["No", "Username", "Nama", "Keanggotaan", "Pemeriksaan", "Perbaikan", "Penambahan", "Login Terakhir"],
            [8, 24, 28, 27, 22, 19, 22, 30],
            [
                (i, u.username, u.nama or u.get_full_name() or u.username, u.keanggotaan, u.jumlah["pemeriksaan"], u.jumlah["perbaikan"],
                 u.jumlah["penambahan"], _tanggal(u.last_login) if u.last_login else "Belum pernah")
                for i, u in enumerate(k["anggota"], start=1)
            ],
        ),
    ]
    # One table per kind of activity, each numbered from 1.
    for jenis, judul in (
        ("Perbaikan", "Perbaikan"), ("Pemeriksaan", "Pemeriksaan"), ("Penambahan", "Penambahan Kendaraan"),
    ):
        baris = [a for a in k["aktivitas"] if a["kegiatan"] == jenis]
        isi += [
            Paragraph(f"Aktivitas Tim — {judul} ({len(baris)})", BAGIAN),
            _tabel_kelompok(
                ["No", "Tanggal", "Kendaraan", "Rincian", "Personil", "Akun"],
                [9, 27, 26, 54, 36, 28],
                [
                    (label, [
                        (i, _tanggal(a["waktu"]), a["kendaraan"], a["rincian"],
                         a["personil"].nama if a["personil"] else "-", a["akun"].username)
                        for i, a in enumerate(isi_golongan, start=1)
                    ])
                    for label, isi_golongan in _per_golongan(baris)
                ],
            ),
        ]
    if len(k["aktivitas"]) >= k["maks_aktivitas"]:
        isi.append(_p(f"Menampilkan {k['maks_aktivitas']} kegiatan terbaru. Persempit periode untuk yang lebih lama."))
    from types import SimpleNamespace
    from .models import Laporan
    biodata = Laporan.objects.filter(akun=ketua).order_by("-dibuat_pada").first()
    isi.append(_tanda_tangan(
        biodata or SimpleNamespace(nama=nama_ketua), "Ketua Tim", "",
    ))
    return _dokumen(isi, f"Laporan Tim {nama_ketua}")


@login_required
def laporan_tim_pdf(request, uid):
    from .laporan_tim import konteks_tim  # laporan_tim imports laporan, which is fine; avoid a cycle at import

    k = konteks_tim(request, uid)
    return _pdf_response(request, buat_pdf_tim(k), f"laporan-tim-{slugify(k['ketua'].username)}.pdf")


def buat_pdf_anggota(k, username):
    """Per-anggota activity report filtered from konteks_tim()."""
    ketua = k["ketua"]
    user = next((u for u in k["anggota"] if u.username == username), None)
    nama_anggota = (getattr(user, "nama", "") or (user.get_full_name() if user else "")) or username
    aktivitas_user = [a for a in k["aktivitas"] if a["akun"].username == username]
    for jenis in ("Pemeriksaan", "Perbaikan", "Penambahan"):
        pass  # filtered per-jenis below
    isi = [
        _kop(
            f"AKTIVITAS ANGGOTA TIM",
            k["keterangan_filter"],
        ),
        Paragraph("Identitas", BAGIAN),
        _tabel_kunci_nilai([
            ("Nama", nama_anggota),
            ("Username", username),
            ("Keanggotaan", getattr(user, "keanggotaan", "-") if user else "-"),
            (getattr(user, "label_nip", "NIP/NRP"), getattr(user, "nip", "-") if user else "-"),
            ("Tim", ketua.get_full_name() or ketua.username),
            ("Periode", k["keterangan_filter"]),
        ]),
    ]
    for jenis in ("Pemeriksaan", "Perbaikan", "Penambahan"):
        rows = [a for a in aktivitas_user if a["kegiatan"] == jenis]
        isi.append(Paragraph(f"{jenis} ({len(rows)})", BAGIAN))
        if rows:
            isi.append(_tabel_data(
                ["No", "Tanggal", "Kendaraan", "Golongan", "Rincian", "Personil"],
                [9, 25, 24, 22, 46, 34],
                [
                    (i, _tanggal(a["waktu"]), a["kendaraan"], a["golongan"], a["rincian"],
                     a["personil"].nama if a["personil"] else "-")
                    for i, a in enumerate(rows, start=1)
                ],
            ))
        else:
            isi.append(_p("Tidak ada data."))
    return _dokumen(isi, f"Aktivitas {nama_anggota}")


@login_required
def laporan_anggota_pdf(request, uid, username):
    from .laporan_tim import konteks_tim

    k = konteks_tim(request, uid)
    return _pdf_response(request, buat_pdf_anggota(k, username), f"aktivitas-{slugify(username)}.pdf")
