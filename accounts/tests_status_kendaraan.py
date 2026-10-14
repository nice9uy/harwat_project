"""A vehicle's status (the dashboard's Siap / Rusak Ringan / Rusak Berat cards)
follows its latest inspection and the repairs made after it."""
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts import golongan
from accounts.models import Laporan, PemeriksaanGolonganB, PemeriksaanGolonganBItem, PerbaikanGolonganB, Satuan
from fleet.models import Vehicle

SIAP, RINGAN, BERAT = Vehicle.Status.SIAP_PAKAI, Vehicle.Status.PERLU_SERVIS, Vehicle.Status.DALAM_PERBAIKAN


class StatusKendaraanTests(TestCase):
    def setUp(self):
        self.vehicle = Vehicle.objects.create(nopol="B 9 ST", merek="Uji", group_kendaraan="B")
        self.orang = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="x.jpg",
        )

    def _periksa(self, kesimpulan, *kondisi):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=self.orang, vehicle=self.vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", kesimpulan=kesimpulan,
        )
        return [
            PemeriksaanGolonganBItem.objects.create(pemeriksaan=hasil, nomor=i, nama_alat=f"Alat {i}", kondisi=k)
            for i, k in enumerate(kondisi, start=1)
        ]

    def test_never_inspected_is_siap(self):
        self.assertEqual(golongan.status_kendaraan(self.vehicle), SIAP)

    def test_follows_the_kesimpulan(self):
        for kesimpulan, kondisi, status in (
            ("siap_pakai", ("B", "ADA"), SIAP),
            ("perlu_perbaikan", ("B", "RR", "RB"), RINGAN),  # the inspector's verdict, even with a part RB
            ("tidak_layak_pakai", ("RB", "B"), BERAT),
            ("siap_pakai", ("B", "RR"), RINGAN),  # a part not Baik can't be Siap
        ):
            self._periksa(kesimpulan, *kondisi)
            self.assertEqual(golongan.status_kendaraan(self.vehicle), status, (kesimpulan, kondisi))

    def test_all_parts_repaired_makes_it_siap_again(self):
        _, ringan, berat = self._periksa("tidak_layak_pakai", "B", "RR", "RB")
        PerbaikanGolonganB.objects.create(teknisi=self.orang, item=ringan, kondisi="B")
        self.assertEqual(golongan.status_kendaraan(self.vehicle), BERAT)  # one part still to repair
        PerbaikanGolonganB.objects.create(teknisi=self.orang, item=berat, kondisi="RR")
        self.assertEqual(golongan.status_kendaraan(self.vehicle), BERAT)  # repaired, but not to Baik
        PerbaikanGolonganB.objects.create(teknisi=self.orang, item=berat, kondisi="B")
        # Nothing left to repair: Siap (there is no "Sudah Diperbaiki" any more).
        self.assertEqual(golongan.perbarui_status(self.vehicle), SIAP)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, SIAP)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        ringkasan = response.context["fleet_summary_kendaraan"]
        self.assertEqual((ringkasan["ready"], ringkasan["service"]), (1, 0))
        self.assertNotIn("repaired", ringkasan)
        self.assertNotContains(response, "Sudah Diperbaiki")
        self.assertContains(self.client.get(reverse("accounts:dashboard_kendaraan"), {"kartu": "siap"}), "B 9 ST")
        self.assertEqual(self.client.get(reverse("accounts:dashboard_kendaraan"), {"kartu": "sudah_diperbaiki"}).status_code, 404)
        # A new inspection starts over.
        self._periksa("siap_pakai", "B")
        self.assertEqual(golongan.status_kendaraan(self.vehicle), SIAP)

    def test_command_recomputes_and_dashboard_counts_it(self):
        self._periksa("perlu_perbaikan", "RR")
        self.assertEqual(Vehicle.objects.get(pk=self.vehicle.pk).status, SIAP)  # saved before the status followed
        call_command("hitung_status_kendaraan", verbosity=0)
        self.assertEqual(Vehicle.objects.get(pk=self.vehicle.pk).status, RINGAN)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        ringkasan = self.client.get(reverse("accounts:dashboard")).context["fleet_summary_kendaraan"]
        self.assertEqual((ringkasan["ready"], ringkasan["due_soon"], ringkasan["in_repair"]), (0, 1, 0))
