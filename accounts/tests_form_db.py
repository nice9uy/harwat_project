"""Form Pemeriksaan <-> database: every input is stored, every column has an input."""
import re
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import golongan
from accounts.models import FOTO_FIELDS, Satuan
from fleet.models import Vehicle

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
# Columns filled by the app, not typed in the form.
OTOMATIS = {"id", "pemeriksa", "dibuat_pada", "pemeriksaan", "nomor", "nama_alat"}


def _nama_input(html):
    return set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="([^"]+)"', html))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FormPemeriksaanSesuaiDatabaseTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")

    def _kolom(self, model):
        return {f.name for f in model._meta.concrete_fields} - OTOMATIS

    def test_every_column_has_an_input_and_every_input_a_column(self):
        for kode, cfg in golongan.GOLONGAN.items():
            with self.subTest(golongan=kode):
                html = self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])).content.decode()
                nama = _nama_input(html)
                header = {n for n in nama if not n.startswith("alat_")}
                # The vehicle comes from the QR scan (hidden input on the page itself).
                self.assertEqual(header | {"vehicle"}, self._kolom(cfg.pemeriksaan_model), kode)
                for nomor, _ in cfg.form.alat:
                    item = {n[len(f"alat_{nomor}_"):] for n in nama if n.startswith(f"alat_{nomor}_")}
                    kolom_item = self._kolom(cfg.item_model)
                    peta = {"jml": "jumlah", "sat": "satuan", "riil": "jumlah_riil", "nyata": "jumlah_nyata"}
                    kolom_input = {peta.get(n, n) for n in item}
                    # The 4 photo slots share one name and fill foto, foto_2..foto_4.
                    if "foto" in kolom_input:
                        kolom_input |= set(FOTO_FIELDS)
                    self.assertEqual(kolom_input, kolom_item, f"{kode} item {nomor}")

    def test_full_submit_round_trips_every_value(self):
        for kode, cfg in golongan.GOLONGAN.items():
            with self.subTest(golongan=kode):
                vehicle = Vehicle.objects.create(nopol=f"T {kode}", merek="Uji", group_kendaraan=kode)
                html = self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])).content.decode()
                data, harap = {"vehicle": vehicle.pk}, {}
                for field in cfg.form._meta.fields:
                    if field == "vehicle":
                        continue
                    model_field = cfg.pemeriksaan_model._meta.get_field(field)
                    if model_field.choices:
                        nilai = model_field.choices[-1][0]
                    elif field == "kesatuan":
                        nilai = self.satuan.pk
                    elif model_field.get_internal_type() in ("PositiveSmallIntegerField", "PositiveIntegerField"):
                        nilai = 77
                    else:
                        nilai = f"isi {field}"
                    self.assertIn(f'name="{field}"', html, f"{kode}: no input for {field}")
                    data[field], harap[field] = nilai, nilai
                for nomor, _ in cfg.form.alat:
                    p = f"alat_{nomor}_"
                    data[p + "kondisi"] = cfg.kondisi[-1][0]
                    data[p + "keterangan"] = f"ket {nomor}"
                    if cfg.pakai_jumlah:
                        data[p + "jml"] = "3"
                    if cfg.pakai_satuan:
                        data.update({p + "sat": "bh", p + "riil": "2", p + "nyata": "1"})
                data["alat_1_foto"] = [SimpleUploadedFile(f"f{i}.gif", GIF, content_type="image/gif") for i in range(4)]
                self.client.get(reverse("accounts:pemeriksaan"))
                response = self.client.post(reverse("accounts:pemeriksaan"), {
                    "nip": "1", "nama": "Uji", "pangkat": "Kapten", "jabatan": "T", "satuan": self.satuan.pk,
                    "foto": SimpleUploadedFile("b.gif", GIF, content_type="image/gif"),
                    "captcha": self.client.session["laporan_captcha"], **data,
                })
                self.assertEqual(response.status_code, 302, response.content.decode()[:2000] if response.status_code != 302 else "")
                hasil = cfg.pemeriksaan_model.objects.get(vehicle=vehicle)
                for field, nilai in harap.items():
                    tersimpan = getattr(hasil, field + "_id" if field == "kesatuan" else field)
                    self.assertEqual(tersimpan, nilai, f"{kode}.{field}")
                self.assertEqual(hasil.items.count(), len(cfg.form.alat))
                item = hasil.items.get(nomor=1)
                self.assertEqual((item.kondisi, item.keterangan), (cfg.kondisi[-1][0], "ket 1"))
                self.assertEqual(len(item.daftar_foto), 4)
                if cfg.pakai_jumlah:
                    self.assertEqual(item.jumlah, 3)
                if cfg.pakai_satuan:
                    self.assertEqual((item.satuan, item.jumlah_riil, item.jumlah_nyata), ("bh", 2, 1))
                self.assertEqual(hasil.pemeriksa.satuan, self.satuan)


class FotoMaksimalTests(TestCase):
    def test_more_than_four_photos_per_part_is_an_error(self):
        from django.utils.datastructures import MultiValueDict

        from accounts.forms import clean_foto

        files = MultiValueDict({"alat_1_foto": [SimpleUploadedFile(f"{i}.gif", GIF, content_type="image/gif") for i in range(5)]})
        errors = []
        self.assertEqual(clean_foto(files, "alat_1_foto", "1. Motor", errors), [])
        self.assertIn("maksimal 4", errors[0])
        errors = []
        files.setlist("alat_1_foto", files.getlist("alat_1_foto")[:4])
        self.assertEqual(len(clean_foto(files, "alat_1_foto", "1. Motor", errors)), 4)
        self.assertEqual(errors, [])
