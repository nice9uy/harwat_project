"""Jeep Diesel: a vehicle group with the Kendaraan Diesel form layout and its
own 112 parts."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts import golongan, roles
from accounts.models import Laporan, PemeriksaanJeepDiesel, PemeriksaanJeepDieselItem, Satuan
from accounts.pemeriksaan import KOMPONEN_JEEP_DIESEL_BERNOMOR
from fleet.models import Vehicle


def _data(vehicle, **overrides):
    data = {
        "vehicle": vehicle.uuid, "km_mil": "120500", "km_berfungsi": "ya", "jam_mesin": "",
        "jam_mesin_berfungsi": "tidak", "buku_pemeliharaan": "ada", "kondisi_ranmor": "jalan",
        "macam_pemeriksaan": "tehnis", "kesimpulan": "siap_pakai",
    }
    for nomor, _ in KOMPONEN_JEEP_DIESEL_BERNOMOR:
        data[f"alat_{nomor}_kondisi"] = "ADA"
    data.update(overrides)
    return data


class JeepDieselTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 4 JD", merek="Jeep", group_kendaraan="jeep")

    def test_is_a_vehicle_group_everywhere(self):
        self.assertEqual(Vehicle.GroupKendaraan("jeep").label, "Jeep Diesel")
        self.assertIn(("jeep", "Jeep Diesel"), roles.FORM_TAMBAH)
        self.assertIs(golongan.for_vehicle(self.vehicle).pemeriksaan_model, PemeriksaanJeepDiesel)
        Laporan.objects.create(
            akun=self.user, nip="1", nama="N", pangkat="P", jabatan="J",
            satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        self.assertContains(self.client.get(reverse("accounts:form_tambah")), 'name="golongan" value="jeep"')
        self.assertContains(self.client.get(reverse("fleet:vehicle_list") + "?group=jeep"), "B 4 JD")

    def test_checklist_has_its_own_112_parts(self):
        self.assertEqual(len(KOMPONEN_JEEP_DIESEL_BERNOMOR), 112)
        response = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["jeep"]))
        for text in ('name="km_mil"', 'name="kondisi_ranmor" value="jalan"',
                     "I. Power Plant", "C. Transfer Case", "C.IV. Electrical System: Aksesoris",
                     "IV. Frame, Suspension, Body, Cab and Hood",
                     "Block Mesin Assy", "Tuas Gigi Low / High", "Pintu Belakang",
                     'name="alat_1_sat"', 'name="alat_112_kondisi" value="ADA"', 'name="alat_112_kondisi" value="TA"'):
            self.assertContains(response, text)
        # Baik on every part, and none of the Kendaraan Diesel parts beyond 112.
        self.assertContains(response, 'value="B"', count=112)
        self.assertContains(response, 'name="alat_112_kondisi" value="B"')
        self.assertNotContains(response, 'name="alat_113_kondisi"')

    def test_form_saves_an_inspection_with_its_items(self):
        cfg = golongan.for_vehicle(self.vehicle)
        form = cfg.form(_data(self.vehicle, alat_1_kondisi="RB", alat_1_sat="bh", alat_1_riil="1", alat_1_nyata="0",
                              alat_1_keterangan="retak"))
        self.assertTrue(form.is_valid(), form.errors)
        hasil = form.save(commit=False)
        hasil.pemeriksa = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil.save()
        for item in form.cleaned_items:
            item.pop("fotos")
            cfg.item_model.objects.create(pemeriksaan=hasil, **item)
        self.assertEqual(PemeriksaanJeepDieselItem.objects.count(), 112)
        pertama = hasil.items.get(nomor=1)
        self.assertEqual(
            (pertama.nama_alat, pertama.kondisi, pertama.satuan, pertama.jumlah_riil, pertama.jumlah_nyata),
            ("Block Mesin Assy", "RB", "bh", 1, 0),
        )
        self.assertEqual(hasil.items.get(nomor=112).nama_alat, "Pintu Belakang")
        self.assertEqual(self.vehicle.pemeriksaan_jeep_diesel.count(), 1)

    def test_baik_is_accepted_and_an_unknown_kondisi_is_not(self):
        cfg = golongan.for_vehicle(self.vehicle)
        self.assertTrue(cfg.form(_data(self.vehicle, alat_5_kondisi="B")).is_valid())
        self.assertFalse(cfg.form(_data(self.vehicle, alat_5_kondisi="HP")).is_valid())


class BanyakFieldTests(TestCase):
    def test_a_diesel_sized_form_is_not_rejected_for_its_field_count(self):
        # Kendaraan Diesel posts about 1300 fields, above Django's default limit of 1000.
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        data = {f"alat_{n}_{kolom}": "" for n in range(1, 142) for kolom in "abcdefghi"}
        response = self.client.post(reverse("accounts:pemeriksaan"), data)
        self.assertEqual(response.status_code, 200)  # re-rendered with its errors, not a 400

    def test_form_errors_also_open_a_popup(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:pemeriksaan")), 'id="judul-galat-pemeriksaan"')
        Laporan.objects.create(
            akun=User.objects.get(username="root"), nip="1", nama="N", pangkat="P", jabatan="J",
            satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        self.client.get(reverse("accounts:pemeriksaan"))
        response = self.client.post(reverse("accounts:pemeriksaan"), {"captcha": self.client.session["laporan_captcha"]})
        self.assertContains(response, 'role="alertdialog"')
        self.assertContains(response, "Pemeriksaan belum tersimpan")
        self.assertContains(response, "Scan QR Code kendaraan terlebih dahulu.", count=2)  # in the page and in the popup
