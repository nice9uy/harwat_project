"""Laporan Pemeriksaan rows open a modal with the vehicle's inspections and inspectors."""
import tempfile

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Laporan, PemeriksaanGolonganB, PemeriksaanGolonganBItem, Satuan
from fleet.models import Vehicle


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanPemeriksaanDetailTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        self.vehicle = Vehicle.objects.create(nopol="B 1 X", merek="Hino", no_chasis="C1", no_mesin="M1")

    def _biodata(self, nip, nama):
        return Laporan.objects.create(
            nip=nip, nama=nama, pangkat="Kapten", jabatan="Teknisi", satuan=self.satuan, foto="x.gif",
        )

    def _pemeriksaan(self, pemeriksa, rusak=1):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", kesatuan=self.satuan,
        )
        for nomor in range(1, 6):
            PemeriksaanGolonganBItem.objects.create(
                pemeriksaan=hasil, nomor=nomor, nama_alat=f"Alat {nomor}", kondisi="RB" if nomor <= rusak else "B",
            )
        return hasil

    def _url(self):
        return reverse("accounts:laporan_pemeriksaan_detail", args=[self.vehicle.pk])

    def test_report_rows_open_the_detail_modal(self):
        hasil = self._pemeriksaan(self._biodata("1", "Budi"))
        response = self.client.get(reverse("accounts:laporan_pemeriksaan"))
        self.assertContains(response, f'hx-get="{self._url()}?pemeriksaan={hasil.pk}"')
        self.assertContains(response, 'id="laporan-modal-body"')

    def test_tabs_list_inspections_and_personnel_once_per_person(self):
        budi, budi_lagi, ani = self._biodata("1", "Budi"), self._biodata("1", "Budi"), self._biodata("2", "Ani")
        pertama = self._pemeriksaan(budi, rusak=2)
        self._pemeriksaan(budi_lagi)
        self._pemeriksaan(ani)
        response = self.client.get(self._url(), {"pemeriksaan": pertama.pk})
        self.assertContains(response, "Riwayat Pemeriksaan")
        self.assertContains(response, "Personil yang Memeriksa")
        self.assertEqual(len(response.context["riwayat"]), 3)
        self.assertEqual(response.context["dipilih"], pertama.pk)
        self.assertContains(response, "Dipilih", count=1)
        personil = {p["biodata"].nip: p["jumlah"] for p in response.context["personil"]}
        self.assertEqual(personil, {"1": 2, "2": 1})
        baris = next(h for h in response.context["riwayat"] if h.pk == pertama.pk)
        self.assertEqual((baris.jumlah_baik, baris.jumlah_perlu), (3, 2))

    def test_query_count_does_not_grow(self):
        self._pemeriksaan(self._biodata("1", "Budi"))

        def hitung():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self._url())
            return len(ctx)
        sedikit = hitung()
        for i in range(4):
            self._pemeriksaan(self._biodata(str(10 + i), f"Orang {i}"))
        self.assertEqual(sedikit, hitung())

    def test_menu_access_follows_laporan_pemeriksaan(self):
        user = User.objects.create_user(username="tim", password="rahasia-123")
        user.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
        self.client.login(username="tim", password="rahasia-123")
        response = self.client.get(self._url())
        self.assertNotEqual(response.status_code, 200)

    def test_report_dates_are_local_time(self):
        from django.utils import timezone

        hasil = self._pemeriksaan(self._biodata("1", "Budi"))
        lokal = timezone.localtime(hasil.dibuat_pada).strftime("%d-%m-%Y %H:%M")
        response = self.client.get(reverse("accounts:laporan_pemeriksaan"))
        self.assertEqual(response.context["halaman"][0][0][0], lokal)

    def test_pdf_export_of_one_inspection(self):
        from accounts.models import PerbaikanGolonganB

        pemeriksa = self._biodata("1", "Budi")
        hasil = self._pemeriksaan(pemeriksa, rusak=2)
        PerbaikanGolonganB.objects.create(teknisi=pemeriksa, item=hasil.items.get(nomor=1), kondisi="B")
        url = reverse("accounts:laporan_pemeriksaan_pdf", args=["B", hasil.pk])
        modal = self.client.get(self._url())
        self.assertContains(modal, f'href="{url}"')
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("inline", response["Content-Disposition"])
        self.assertIn("attachment", self.client.get(url, {"unduh": 1})["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=["x", hasil.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=["diesel", hasil.pk])).status_code, 404)

    def test_pdf_for_every_group(self):
        from accounts.models import PemeriksaanBermotor, PemeriksaanBermotorItem, PemeriksaanDiesel, PemeriksaanDieselItem

        pemeriksa = self._biodata("1", "Budi")
        bermotor = PemeriksaanBermotor.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, buku_harian="ada", macam_pemeriksaan="tehnis",
        )
        PemeriksaanBermotorItem.objects.create(pemeriksaan=bermotor, nomor=1, nama_alat="Mesin", kondisi="HP")
        diesel = PemeriksaanDiesel.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, km_berfungsi="ya", jam_mesin_berfungsi="ya",
            buku_pemeliharaan="ada", kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        PemeriksaanDieselItem.objects.create(
            pemeriksaan=diesel, nomor=1, nama_alat="Radiator", satuan="bh", jumlah_riil=1, jumlah_nyata=1, kondisi="ADA",
        )
        for kode, hasil in (("bermotor", bermotor), ("diesel", diesel)):
            response = self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=[kode, hasil.pk]))
            self.assertEqual(response.status_code, 200, kode)
            self.assertTrue(response.content.startswith(b"%PDF"), kode)
