"""Every table shows at most 15 rows per page, with page links that keep the filters."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Satuan
from accounts.paging import PER_HALAMAN
from fleet.models import Jadwal, Servis, Vehicle


class PagingTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.vehicles = [
            Vehicle.objects.create(nopol=f"B {i:02d} X", merek="Hino", no_chasis=f"C{i}", no_mesin=f"M{i}")
            for i in range(PER_HALAMAN + 5)
        ]

    def _jumlah(self, response, kunci):
        return len(response.context[kunci].object_list)

    def test_armada_pages(self):
        url = reverse("fleet:vehicle_list")
        pertama = self.client.get(url)
        self.assertEqual(self._jumlah(pertama, "vehicles"), PER_HALAMAN)
        self.assertContains(pertama, "Menampilkan 1–15 dari 20 data")
        kedua = self.client.get(url, {"group": "B", "page": 2})
        self.assertEqual(self._jumlah(kedua, "vehicles"), 5)
        self.assertContains(kedua, "Menampilkan 16–20 dari 20 data")
        # Numbering continues on the next page.
        self.assertContains(kedua, ">16</td>")

    def test_search_page_links_reload_only_results(self):
        response = self.client.get(reverse("fleet:vehicle_search"), {"q": "B"})
        self.assertEqual(self._jumlah(response, "vehicles"), PER_HALAMAN)
        self.assertContains(response, 'hx-target="#vehicle-search-hasil"')
        self.assertContains(response, "q=B&amp;hasil=1&amp;page=2")
        kedua = self.client.get(reverse("fleet:vehicle_search"), {"q": "B", "hasil": 1, "page": 2})
        self.assertTemplateUsed(kedua, "fleet/_vehicle_search_hasil.html")
        self.assertEqual(self._jumlah(kedua, "vehicles"), 5)

    def test_jadwal_and_servis_pages(self):
        for v in self.vehicles:
            Jadwal.objects.create(vehicle=v, tanggal="2026-10-01", kegiatan="servis")
            Servis.objects.create(vehicle=v, tanggal="2026-09-01", jenis_servis="Oli", biaya=1000)
        jadwal = self.client.get(reverse("operasional:jadwal_list"))
        self.assertEqual(self._jumlah(jadwal, "jadwal_list"), PER_HALAMAN)
        servis = self.client.get(reverse("operasional:servis_list"), {"page": 2})
        self.assertEqual(self._jumlah(servis, "servis_list"), 5)
        # The total covers every page, not just the one shown.
        self.assertEqual(servis.context["total_biaya"], 20000)

    def test_pengaturan_tabs_page_independently(self):
        for i in range(PER_HALAMAN + 3):
            Satuan.objects.create(nama=f"Satuan {i:02d}")
        response = self.client.get(reverse("accounts:pengaturan"), {"hal_satuan": 2, "tab": "satuan"})
        self.assertEqual(self._jumlah(response, "satuan_list"), 3)
        self.assertEqual(response.context["users"].number, 1)
        self.assertEqual(response.context["tab"], "satuan")
        self.assertContains(response, "tab=satuan&amp;hal_satuan=1")

    def test_laporan_penambahan_pages(self):
        response = self.client.get(reverse("accounts:laporan_penambahan"))
        self.assertEqual(self._jumlah(response, "halaman"), PER_HALAMAN)
        self.assertContains(response, "Menampilkan 1–15 dari 20 data")
