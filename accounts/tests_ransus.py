"""RANSUS: a vehicle group with the Kendaraan Diesel form header and its own
list of 40 pieces of equipment."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts import golongan, km_jadwal
from accounts.models import Laporan, PemeriksaanRansus, PemeriksaanRansusItem, PerbaikanRansus, Satuan
from accounts.pemeriksaan import KOMPONEN_RANSUS_BERNOMOR
from fleet.models import Vehicle


def _data(vehicle, **overrides):
    data = {
        "vehicle": vehicle.uuid, "km_mil": "1200", "km_berfungsi": "ya", "jam_mesin": "",
        "jam_mesin_berfungsi": "tidak", "buku_pemeliharaan": "ada", "kondisi_ranmor": "jalan",
        "macam_pemeriksaan": "tehnis", "kesimpulan": "siap_pakai",
    }
    for nomor, _ in KOMPONEN_RANSUS_BERNOMOR:
        data[f"alat_{nomor}_kondisi"] = "B"
    data.update(overrides)
    return data


class RansusTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="RS 01", merek="Damkar", group_kendaraan="ransus")

    def test_checklist_lists_the_40_pieces_of_equipment(self):
        self.assertEqual(len(KOMPONEN_RANSUS_BERNOMOR), 40)
        self.assertEqual(KOMPONEN_RANSUS_BERNOMOR[0], (1, 'Selang Penyalur (Fire Hose) Ukuran 2½" x 20 Meter'))
        self.assertEqual(KOMPONEN_RANSUS_BERNOMOR[-1], (40, "Toolkit Unit"))
        self.assertIs(golongan.for_vehicle(self.vehicle).pemeriksaan_model, PemeriksaanRansus)
        self.assertIn(Vehicle.GroupKendaraan.RANSUS, km_jadwal.KM_GOLONGAN)
        response = self.client.get(reverse("accounts:pemeriksaan_checklist", args=["ransus"]))
        for text in ("I. Peralatan", "Saringan Rotan", "Alat Pelindung Pernapasan (SCBA)", "Toolkit Unit",
                     'name="km_mil"', 'name="alat_40_kondisi" value="B"', 'name="alat_40_kondisi" value="RB"'):
            self.assertContains(response, text)
        self.assertNotContains(response, 'name="alat_41_kondisi"')
        # RANUM has no form yet.
        self.assertEqual(self.client.get(reverse("accounts:pemeriksaan_checklist", args=["ranum"])).status_code, 404)

    def test_form_saves_an_inspection_and_its_repairs(self):
        cfg = golongan.for_vehicle(self.vehicle)
        form = cfg.form(_data(self.vehicle, alat_7_kondisi="RB", alat_7_keterangan="patah"))
        self.assertTrue(form.is_valid(), form.errors)
        bio = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        hasil = form.save(commit=False)
        hasil.pemeriksa = bio
        hasil.save()
        for item in form.cleaned_items:
            item.pop("fotos")
            cfg.item_model.objects.create(pemeriksaan=hasil, **item)
        self.assertEqual(PemeriksaanRansusItem.objects.count(), 40)
        rusak = hasil.items.get(nomor=7)
        self.assertEqual((rusak.nama_alat, rusak.kondisi, rusak.keterangan), ("Kunci Hidran", "RB", "patah"))
        self.assertEqual(self.vehicle.pemeriksaan_ransus.count(), 1)
        PerbaikanRansus.objects.create(teknisi=bio, item=rusak, kondisi="B")
        self.assertEqual(cfg.perbaikan_model.objects.get().item, rusak)
        # A damaged part needs a photo or a note.
        self.assertFalse(cfg.form(_data(self.vehicle, alat_7_kondisi="RB")).is_valid())
