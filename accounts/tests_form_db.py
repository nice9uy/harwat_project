"""Form Pemeriksaan <-> database: every input is stored, every column has an input."""
import re
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import golongan
from accounts.models import FOTO_FIELDS, Laporan, Satuan
from fleet.models import Vehicle

GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
# Columns filled by the app, not typed in the form.
OTOMATIS = {"id", "uuid", "pemeriksa", "dibuat_pada", "pemeriksaan", "nomor", "nama_alat"}
# Columns whose inputs sit on the page itself, not in the group's checklist:
# the scanned vehicle, plus kesimpulan and keterangan in the Lanjutkan modal.
DI_HALAMAN = {"vehicle", "kesimpulan", "keterangan"}
# Columns kept for old records whose input was taken off the form.
TIDAK_DITANYA = {"buku_jalan"}


def _nama_input(html):
    return set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="([^"]+)"', html))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FormPemeriksaanSesuaiDatabaseTests(TestCase):
    def setUp(self):
        root = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        # The pemeriksa's biodata comes from Info Profil, not the form.
        Laporan.objects.create(
            akun=root, nip="1", nama="Uji", pangkat="Kapten", jabatan="T", satuan=self.satuan,
            foto=SimpleUploadedFile("b.gif", GIF, content_type="image/gif"),
        )

    def _kolom(self, model):
        return {f.name for f in model._meta.concrete_fields} - OTOMATIS

    def test_every_column_has_an_input_and_every_input_a_column(self):
        for kode, cfg in golongan.GOLONGAN.items():
            with self.subTest(golongan=kode):
                html = self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])).content.decode()
                nama = _nama_input(html)
                header = {n for n in nama if not n.startswith("alat_")}
                self.assertEqual(header | DI_HALAMAN, self._kolom(cfg.pemeriksaan_model) - TIDAK_DITANYA, kode)
                for nomor, _ in cfg.form.alat:
                    item = {n[len(f"alat_{nomor}_"):] for n in nama if n.startswith(f"alat_{nomor}_")}
                    kolom_item = self._kolom(cfg.item_model)
                    peta = {"jml": "jumlah", "sat": "satuan", "riil": "jumlah_riil", "nyata": "jumlah_nyata"}
                    kolom_input = {peta.get(n, n) for n in item}
                    # The 4 photo slots share one name and fill foto, foto_2..foto_4.
                    if "foto" in kolom_input:
                        kolom_input |= set(FOTO_FIELDS)
                    self.assertEqual(kolom_input, kolom_item, f"{kode} item {nomor}")

    def test_page_has_inputs_outside_the_checklist(self):
        html = self.client.get(reverse("accounts:pemeriksaan")).content.decode()
        self.assertLessEqual(DI_HALAMAN, _nama_input(html) | {"vehicle"})

    def test_full_submit_round_trips_every_value(self):
        for kode, cfg in golongan.GOLONGAN.items():
            with self.subTest(golongan=kode):
                vehicle = Vehicle.objects.create(nopol=f"T {kode}", merek="Uji", group_kendaraan=kode)
                html = self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])).content.decode()
                data, harap, foto = {"vehicle": vehicle.uuid}, {}, []
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
                    elif model_field.get_internal_type() == "FileField":
                        # A photo (the odometer's): uploaded, stored compressed under a name of its own.
                        self.assertIn(f'name="{field}"', html, f"{kode}: no input for {field}")
                        data[field] = SimpleUploadedFile(f"{field}.gif", GIF, content_type="image/gif")
                        foto.append(field)
                        continue
                    else:
                        nilai = f"isi {field}"
                    if field not in DI_HALAMAN:
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
                self.client.post(reverse("accounts:pemeriksaan_draft", args=[vehicle.uuid]), {"x": "1"}, content_type="application/json")
                self.client.get(reverse("accounts:pemeriksaan"))
                response = self.client.post(reverse("accounts:pemeriksaan"), {
                    "captcha": self.client.session["laporan_captcha"], **data,
                })
                self.assertEqual(response.status_code, 302, response.content.decode()[:2000] if response.status_code != 302 else "")
                hasil = cfg.pemeriksaan_model.objects.get(vehicle=vehicle)
                # Submitting clears the saved draft.
                self.assertEqual(self.client.get(reverse("accounts:pemeriksaan_draft", args=[vehicle.uuid])).json(), {})
                for field, nilai in harap.items():
                    tersimpan = getattr(hasil, field + "_id" if field == "kesatuan" else field)
                    self.assertEqual(tersimpan, nilai, f"{kode}.{field}")
                for field in foto:
                    self.assertTrue(getattr(hasil, field), f"{kode}.{field}")
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


class DraftPemeriksaanTests(TestCase):
    def setUp(self):
        # Not a superuser: a superuser's form isn't auto-saved (accounts.status.dicatat).
        self.user = User.objects.create_user(username="pemeriksa", password="rahasia-123")
        self.client.login(username="pemeriksa", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 1 DR", merek="Uji", group_kendaraan=Vehicle.GroupKendaraan.GOLONGAN_B)
        self.url = reverse("accounts:pemeriksaan_draft", args=[self.vehicle.uuid])

    def _simpan(self, data):
        return self.client.post(self.url, data, content_type="application/json")

    def test_saved_draft_comes_back_for_the_same_user_only(self):
        self.assertEqual(self._simpan({"alat_1_kondisi": "B", "keterangan": "catatan"}).json(), {"ok": True})
        self.assertEqual(self.client.get(self.url).json(), {"alat_1_kondisi": "B", "keterangan": "catatan"})
        self._simpan({"alat_1_kondisi": "RR"})
        self.assertEqual(self.client.get(self.url).json(), {"alat_1_kondisi": "RR"})
        User.objects.create_user(username="lain", password="rahasia-123")
        self.client.login(username="lain", password="rahasia-123")
        self.assertEqual(self.client.get(self.url).json(), {})

    def test_rejects_non_object_or_huge_body(self):
        self.assertEqual(self._simpan(["x"]).status_code, 400)
        self.assertEqual(self._simpan({"x": "a" * 600_000}).status_code, 400)

    def test_page_uses_the_server_draft(self):
        html = self.client.get(reverse("accounts:pemeriksaan")).content.decode()
        self.assertIn(reverse("accounts:pemeriksaan_draft", args=["00000000-0000-0000-0000-000000000000"]), html)


class DashboardSedangDikerjakanTests(TestCase):
    def test_lists_unfinished_inspections_with_progress(self):
        from accounts.models import DraftPemeriksaan
        root = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        vehicle = Vehicle.objects.create(nopol="B 5 DK", merek="Hino", group_kendaraan=Vehicle.GroupKendaraan.GOLONGAN_B)
        DraftPemeriksaan.objects.create(
            vehicle=vehicle, pemeriksa=root, data={"alat_1_kondisi": "B", "alat_2_kondisi": "RR", "alat_3_kondisi": ""},
        )
        total = len(golongan.GOLONGAN[vehicle.group_kendaraan].form.alat)
        response = self.client.get(reverse("accounts:dashboard_partial"))  # the Kegiatan tab's part
        self.assertContains(response, "Sedang Dikerjakan")
        self.assertContains(response, "Pemeriksaan B 5 DK")
        self.assertContains(response, f"2/{total} item")


class KondisiBaikTests(TestCase):
    def test_baik_and_ada_need_no_repair_in_every_group(self):
        from accounts.views import _perlu_perbaikan
        akun = User.objects.create_user(username="p", password="x")
        satuan = Satuan.objects.create(nama="Yonif 1")
        biodata = Laporan.objects.create(
            akun=akun, nip="1", nama="P", pangkat="K", jabatan="T", satuan=satuan,
            foto=SimpleUploadedFile("b.gif", GIF, content_type="image/gif"),
        )
        for kode, cfg in golongan.GOLONGAN.items():
            with self.subTest(golongan=kode):
                self.assertEqual(set(cfg.baik), {"B", "ADA"})
                vehicle = Vehicle.objects.create(nopol=f"K {kode}", merek="Uji", group_kendaraan=kode)
                # Required choice fields; the rest are blank or nullable.
                wajib = {
                    f.name: f.choices[0][0] for f in cfg.pemeriksaan_model._meta.concrete_fields
                    if f.choices and not f.has_default()
                }
                hasil = cfg.pemeriksaan_model.objects.create(pemeriksa=biodata, vehicle=vehicle, **wajib)
                for nomor, kondisi in enumerate(["B", "ADA", "RR"], start=1):
                    cfg.item_model.objects.create(pemeriksaan=hasil, nomor=nomor, nama_alat=f"Alat {nomor}", kondisi=kondisi)
                self.assertEqual([i.kondisi for i in _perlu_perbaikan(vehicle, hasil)], ["RR"])
