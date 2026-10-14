"""Dashboard card Perlu Servis: vehicles past the Interval KM or Waktu Servis
set in Pengaturan > KM for their group."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import km_jadwal
from accounts.models import KmJadwal, Laporan, PemeriksaanGolonganB, Satuan
from fleet.models import Servis, Vehicle


class PerluServisTests(TestCase):
    def setUp(self):
        self.orang = Laporan.objects.create(
            nip="1", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S"), foto="x.jpg",
        )
        self.vehicle = Vehicle.objects.create(nopol="B 1 SV", merek="Uji", group_kendaraan="B")
        self.aturan = KmJadwal.objects.get(komponen="KM Kendaraan")

    def _atur(self, km=None, bulan=None):
        self.aturan.interval_km, self.aturan.interval_bulan = km, bulan
        self.aturan.save()

    def _periksa(self, km, hari_lalu=0):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=self.orang, vehicle=self.vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", km_kendaraan=km,
        )
        PemeriksaanGolonganB.objects.filter(pk=hasil.pk).update(dibuat_pada=timezone.now() - timedelta(days=hari_lalu))

    def _jatuh_tempo(self):
        return km_jadwal.perlu_servis([Vehicle.objects.get(pk=self.vehicle.pk)])

    def test_never_due_while_no_interval_is_set(self):
        self._periksa(999999)
        self.assertEqual(self._jatuh_tempo(), {})

    def test_due_by_km_since_the_last_service(self):
        self._atur(km=5000)
        self._periksa(4000, hari_lalu=60)
        self.assertEqual(self._jatuh_tempo(), {})  # 4000 km since new
        self._periksa(5200, hari_lalu=40)
        self.assertIn("5200 km", self._jatuh_tempo()[self.vehicle.pk])
        # Serviced after that reading: the count starts again from 5200.
        Servis.objects.create(vehicle=self.vehicle, tanggal=timezone.localdate() - timedelta(days=30), jenis_servis="Oli")
        self.assertEqual(self._jatuh_tempo(), {})
        self._periksa(9000, hari_lalu=5)
        self.assertEqual(self._jatuh_tempo(), {})  # 3800 km since the service
        self._periksa(10300)
        self.assertIn("5100 km sejak servis terakhir", self._jatuh_tempo()[self.vehicle.pk])

    def test_due_by_months_since_the_last_service_or_since_added(self):
        self._atur(bulan=6)
        self.assertEqual(self._jatuh_tempo(), {})  # just added
        Vehicle.objects.filter(pk=self.vehicle.pk).update(dibuat_pada=timezone.now() - timedelta(days=200))
        self.assertIn("bulan sejak ditambahkan", self._jatuh_tempo()[self.vehicle.pk])
        Servis.objects.create(vehicle=self.vehicle, tanggal=timezone.localdate() - timedelta(days=20), jenis_servis="Oli")
        self.assertEqual(self._jatuh_tempo(), {})

    def test_each_group_uses_its_own_row(self):
        self._atur(km=1000)
        self._periksa(5000)
        diesel = Vehicle.objects.create(nopol="B 2 SV", merek="Uji", group_kendaraan="diesel")
        self.assertEqual(set(km_jadwal.perlu_servis(Vehicle.objects.all())), {self.vehicle.pk})
        self.assertNotIn(diesel.pk, km_jadwal.perlu_servis(Vehicle.objects.all()))

    def test_dashboard_card_and_its_table(self):
        self._atur(km=1000)
        self._periksa(5000)
        Vehicle.objects.create(nopol="B 3 SV", merek="Uji", group_kendaraan="B")
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.context["fleet_summary_kendaraan"]["service"], 1)
        self.assertContains(response, "Perlu Servis</th>")  # the Semua Matra table
        url = reverse("accounts:dashboard_kendaraan")
        tabel = self.client.get(url, {"kartu": "perlu_servis"})
        self.assertContains(tabel, "B 1 SV")
        self.assertNotContains(tabel, "B 3 SV")
        self.assertContains(tabel, ">Jatuh Tempo</th>")
        self.assertContains(tabel, "5000 km sejak awal")
        self.assertNotContains(self.client.get(url, {"kartu": "siap"}), ">Jatuh Tempo</th>")


class PerluServisKomponenTests(TestCase):
    """A vehicle with parts still to repair is due a service, intervals or not."""

    def test_unrepaired_parts_make_it_due_until_repaired_to_baik(self):
        from accounts.models import PemeriksaanGolonganBItem, PerbaikanGolonganB
        orang = Laporan.objects.create(nip="2", nama="N", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="S2"))
        vehicle = Vehicle.objects.create(nopol="B 2 SV", merek="Uji", group_kendaraan="B")
        baik = Vehicle.objects.create(nopol="B 3 SV", merek="Uji", group_kendaraan="B")

        def periksa(kendaraan, *kondisi):
            hasil = PemeriksaanGolonganB.objects.create(
                pemeriksa=orang, vehicle=kendaraan, pembagian_kelas="1", eselon_reparasi="1",
                macam_pemeriksaan="tehnis", buku_jalan="ada",
            )
            return [
                PemeriksaanGolonganBItem.objects.create(pemeriksaan=hasil, nomor=n, nama_alat=f"Alat {n}", kondisi=k)
                for n, k in enumerate(kondisi, start=1)
            ]

        def tempo():
            return km_jadwal.perlu_servis(Vehicle.objects.filter(pk__in=[vehicle.pk, baik.pk]))

        periksa(baik, "B", "B")
        rem, lampu, _ = periksa(vehicle, "RB", "RR", "B")
        self.assertEqual(tempo(), {vehicle.pk: "2 komponen belum diperbaiki"})
        # A repair that leaves the part not Baik doesn't settle it; one to Baik does.
        PerbaikanGolonganB.objects.create(teknisi=orang, item=rem, kondisi="RR")
        self.assertEqual(tempo(), {vehicle.pk: "2 komponen belum diperbaiki"})
        PerbaikanGolonganB.objects.create(teknisi=orang, item=rem, kondisi="B")
        self.assertEqual(tempo(), {vehicle.pk: "1 komponen belum diperbaiki"})
        PerbaikanGolonganB.objects.create(teknisi=orang, item=lampu, kondisi="B")
        self.assertEqual(tempo(), {})
        # Only the last inspection counts: a clean one after it clears the vehicle.
        periksa(vehicle, "RB")
        self.assertEqual(tempo(), {vehicle.pk: "1 komponen belum diperbaiki"})
        periksa(vehicle, "B")
        self.assertEqual(tempo(), {})
        # The dashboard card counts it.
        periksa(vehicle, "RR")
        User.objects.create_superuser(username="root_ps", password="rahasia-123")
        self.client.login(username="root_ps", password="rahasia-123")
        self.assertEqual(self.client.get(reverse("accounts:dashboard")).context["fleet_summary_kendaraan"]["service"], 1)
