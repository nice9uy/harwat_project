"""Golongan B inspection: the KM Kendaraan field and its photo."""
import io
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from PIL import Image

from accounts import golongan
from accounts.models import Laporan, Satuan
from fleet.models import Vehicle


def _foto():
    data = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(data, "PNG")
    return SimpleUploadedFile("odometer.png", data.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GolonganBKmTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 5 KM", merek="Uji", group_kendaraan="B")
        self.cfg = golongan.for_vehicle(self.vehicle)

    def _data(self, **ganti):
        data = {
            "vehicle": self.vehicle.uuid, "pembagian_kelas": "1", "eselon_reparasi": "1",
            "macam_pemeriksaan": "tehnis", "buku_jalan": "ada", "kesimpulan": "siap_pakai",
        }
        for nomor, _ in self.cfg.form.alat:
            data[f"alat_{nomor}_kondisi"] = "B"
            data[f"alat_{nomor}_jml"] = "1"
        data.update(ganti)
        return data

    def _simpan(self, form):
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil.save()
        return hasil

    def test_checklist_has_the_km_field_and_photo_before_kesatuan(self):
        content = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["B"])).content.decode()
        self.assertIn('name="km_kendaraan"', content)
        # Marked * like the other parts that go into the Jadwal.
        self.assertIn('KM Kendaraan<span class="ml-0.5 font-bold text-red-500" title="Masuk ke Jadwal untuk dicek">*</span>', content)
        self.assertIn('name="foto_km"', content)
        self.assertNotIn('name="buku_jalan"', content)  # Buku Jalan was taken off the form
        self.assertLess(content.index('name="macam_pemeriksaan"'), content.index('name="km_kendaraan"'))
        self.assertLess(content.index('name="foto_km"'), content.index('id="kesatuan"'))

    def test_km_and_photo_are_saved_and_shown_in_history(self):
        hasil = self._simpan(self.cfg.form(self._data(km_kendaraan="45210"), MultiValueDict({"foto_km": [_foto()]})))
        self.assertEqual(hasil.km_kendaraan, 45210)
        self.assertTrue(hasil.foto_km.name.endswith(".jpg"))  # compressed like every upload
        self.assertIn("KM 45210", hasil.ringkasan())
        riwayat = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 5 KM"})
        self.assertContains(riwayat, "KM 45210")
        self.assertContains(riwayat, hasil.foto_km.url)

    def test_both_are_optional(self):
        hasil = self._simpan(self.cfg.form(self._data()))
        self.assertIsNone(hasil.km_kendaraan)
        self.assertFalse(hasil.foto_km)
        self.assertEqual(hasil.buku_jalan, "")
        self.assertNotIn("Buku jalan", hasil.ringkasan())
        self.assertNotIn("KM", hasil.ringkasan())
        self.assertFalse(self.cfg.form(self._data(km_kendaraan="-5")).is_valid())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DieselFotoKmTests(TestCase):
    """Kendaraan Diesel and Jeep Diesel: a photo under Km / Mil."""

    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 6 DS", merek="Uji", group_kendaraan="diesel")
        self.cfg = golongan.for_vehicle(self.vehicle)

    def _data(self):
        data = {
            "vehicle": self.vehicle.uuid, "km_mil": "120500", "km_berfungsi": "ya", "jam_mesin": "",
            "jam_mesin_berfungsi": "tidak", "buku_pemeliharaan": "ada", "kondisi_ranmor": "jalan",
            "macam_pemeriksaan": "tehnis", "kesimpulan": "siap_pakai",
        }
        for nomor, _ in self.cfg.form.alat:
            data[f"alat_{nomor}_kondisi"] = "B"
        return data

    def test_upload_sits_under_km_mil_on_both_diesel_forms(self):
        for kode in ("diesel", "jeep"):
            content = self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])).content.decode()
            self.assertLess(content.index('name="km_mil"'), content.index('name="foto_km"'), kode)
            self.assertLess(content.index('name="foto_km"'), content.index('name="km_berfungsi"'), kode)

    def test_km_mil_is_marked_on_both_diesel_forms(self):
        tanda = 'title="Masuk ke Jadwal untuk dicek">*</span>'
        for kode in ("diesel", "jeep"):
            self.assertContains(self.client.get(reverse("accounts:pemeriksaan_checklist", args=[kode])), tanda, count=1)

    def test_jeep_diesel_saves_the_photo_too(self):
        jeep = Vehicle.objects.create(nopol="B 7 JP", merek="Uji", group_kendaraan="jeep")
        cfg = golongan.for_vehicle(jeep)
        data = {**self._data(), "vehicle": jeep.uuid}
        for kunci in [k for k in data if k.startswith("alat_")]:
            del data[kunci]
        for nomor, _ in cfg.form.alat:
            data[f"alat_{nomor}_kondisi"] = "B"
        form = cfg.form(data, MultiValueDict({"foto_km": [_foto()]}))
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="2", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S2"), foto="laporan/x.jpg",
        )
        hasil.save()
        self.assertTrue(hasil.foto_km.name.endswith(".jpg"))
        self.assertContains(self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 7 JP"}), hasil.foto_km.url)

    def test_photo_is_saved_and_linked_in_history(self):
        form = self.cfg.form(self._data(), MultiValueDict({"foto_km": [_foto()]}))
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil.save()
        self.assertTrue(hasil.foto_km.name.endswith(".jpg"))
        riwayat = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 6 DS"})
        self.assertContains(riwayat, hasil.foto_km.url)
        # Optional.
        self.assertTrue(self.cfg.form(self._data()).is_valid())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BermotorOliKmTests(TestCase):
    """Motor: KM Kendaraan with its photo, and the oil parts marked *."""

    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 8 OL", merek="Uji", group_kendaraan="bermotor")
        self.cfg = golongan.for_vehicle(self.vehicle)
        self.oli = {nama: nomor for nomor, nama in self.cfg.form.alat if nama.startswith("Oli ")}

    def _data(self, **ganti):
        data = {
            "vehicle": self.vehicle.uuid, "buku_harian": "ada", "macam_pemeriksaan": "tehnis",
            "kesimpulan": "siap_pakai",
        }
        for nomor, _ in self.cfg.form.alat:
            data[f"alat_{nomor}_kondisi"] = "B"
        data.update(ganti)
        return data

    def test_km_kendaraan_with_photo_sits_under_bbm(self):
        content = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["bermotor"])).content.decode()
        self.assertLess(content.index('name="bbm"'), content.index('name="km_kendaraan"'))
        self.assertLess(content.index('name="foto_km"'), content.index('name="buku_harian"'))
        self.assertIn('KM Kendaraan<span class="ml-0.5 font-bold text-red-500" title="Masuk ke Jadwal untuk dicek">*</span>', content)
        form = self.cfg.form(self._data(km_kendaraan="45210"), MultiValueDict({"foto_km": [_foto()]}))
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil.save()
        self.assertEqual(hasil.km_kendaraan, 45210)
        self.assertTrue(hasil.foto_km.name.endswith(".jpg"))
        riwayat = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 8 OL"})
        self.assertContains(riwayat, "KM 45210")
        self.assertContains(riwayat, hasil.foto_km.url)

    def test_oil_parts_are_marked_and_keep_their_four_photos(self):
        self.assertEqual(sorted(self.oli), ["Oli Gardan", "Oli Mesin", "Oli Persneling / Transmisi"])
        content = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["bermotor"])).content.decode()
        for nomor in self.oli.values():
            self.assertNotIn(f'name="alat_{nomor}_km"', content)
            self.assertEqual(content.count(f'name="alat_{nomor}_foto"'), 4)
        # They carry the * that marks parts going into the Jadwal, explained under the list.
        self.assertEqual(content.count('title="Masuk ke Jadwal untuk dicek">*</span>'), 4)  # 3 oil parts + KM Kendaraan
        self.assertIn("Masuk ke Jadwal untuk dicek.</p>", content)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class BatasPanjangTests(TestCase):
    """Limits a long text or a long photo file name used to trip in Form Pemeriksaan."""

    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 9 PJ", merek="Uji", group_kendaraan="bermotor")
        self.cfg = golongan.for_vehicle(self.vehicle)

    def _data(self, **ganti):
        data = {"vehicle": self.vehicle.uuid, "buku_harian": "ada", "macam_pemeriksaan": "tehnis", "kesimpulan": "siap_pakai"}
        for nomor, _ in self.cfg.form.alat:
            data[f"alat_{nomor}_kondisi"] = "B"
        return {**data, **ganti}

    def test_a_photo_with_a_very_long_file_name_is_accepted_and_renamed_short(self):
        foto = _foto()
        foto.name = "IMG_" + "a" * 180 + ".png"
        form = self.cfg.form(self._data(km_kendaraan="10"), MultiValueDict({"foto_km": [foto]}))
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil.save()
        self.assertLess(len(hasil.foto_km.name), 100)

    def test_an_overlong_text_names_its_field_and_inputs_carry_their_limit(self):
        form = self.cfg.form(self._data(bbm="x" * 120))
        self.assertFalse(form.is_valid())
        self.assertTrue(any(g.startswith("BBM: ") and "100" in g for g in form.daftar_galat), form.daftar_galat)
        html = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["bermotor"])).content.decode()
        for nama, maks in (("bbm", 100), ("tempat_pemeriksaan", 150), ("ukuran_ban", 50)):
            self.assertIn(f'name="{nama}" maxlength="{maks}"', html)
