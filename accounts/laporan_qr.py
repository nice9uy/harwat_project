"""The QR codes of a report's vehicles as a Word document, to print and cut."""
import io

from django.http import HttpResponse
from django.utils import timezone
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt

from fleet.qr import qr_png_with_logo

KOLOM = 3
LEBAR_QR = Mm(52)


def qr_word(judul, kendaraan, nama_file):
    """A4 sheet(s) with a grid of ``kendaraan``'s QR codes (the same image as
    on the vehicle list: Kemhan logo, No. Registrasi underneath), each over
    its Merk/Type."""
    doc = Document()
    bagian = doc.sections[0]
    bagian.page_width, bagian.page_height = Mm(210), Mm(297)
    bagian.left_margin = bagian.right_margin = Mm(15)
    bagian.top_margin = bagian.bottom_margin = Mm(15)

    kepala = doc.add_paragraph()
    kepala.alignment = WD_ALIGN_PARAGRAPH.CENTER
    teks = kepala.add_run(f"QR Code — {judul}")
    teks.bold = True
    teks.font.size = Pt(14)
    ket = doc.add_paragraph()
    ket.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ket.add_run(f"{len(kendaraan)} kendaraan · dicetak {timezone.localtime():%d-%m-%Y %H:%M}").font.size = Pt(9)

    if not kendaraan:
        doc.add_paragraph("Tidak ada data untuk filter ini.").alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        tabel = doc.add_table(rows=-(-len(kendaraan) // KOLOM), cols=KOLOM)
        tabel.style = "Table Grid"
        tabel.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, v in enumerate(kendaraan):
            sel = tabel.cell(i // KOLOM, i % KOLOM)
            gambar = sel.paragraphs[0]
            gambar.alignment = WD_ALIGN_PARAGRAPH.CENTER
            gambar.add_run().add_picture(io.BytesIO(qr_png_with_logo(v.qr_text(), label=v.nopol)), width=LEBAR_QR)
            bawah = sel.add_paragraph()
            bawah.alignment = WD_ALIGN_PARAGRAPH.CENTER
            bawah.add_run(v.merek).font.size = Pt(9)

    isi = io.BytesIO()
    doc.save(isi)
    response = HttpResponse(
        isi.getvalue(), content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = f'attachment; filename="{nama_file}"'
    return response
