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

    def test_pengaturan_tabs_page_independently(self):
        for i in range(PER_HALAMAN + 3):
            Satuan.objects.create(nama=f"Satuan {i:02d}")
        response = self.client.get(reverse("accounts:pengaturan"), {"hal_satuan": 2, "tab": "satuan"})
        self.assertEqual(self._jumlah(response, "satuan_list"), 3)
        self.assertEqual(response.context["users"].number, 1)
        self.assertEqual(response.context["tab"], "satuan")
        self.assertContains(response, "tab=satuan&amp;matra=darat&amp;hal_satuan=1")

    def test_laporan_penambahan_pages(self):
        response = self.client.get(reverse("accounts:laporan_penambahan"))
        self.assertEqual(self._jumlah(response, "halaman"), PER_HALAMAN)
        self.assertContains(response, "Menampilkan 1–15 dari 20 data")


class CariSatuanTests(TestCase):
    """Pengaturan > Satuan: the search field narrows the matra's units."""

    def test_search_by_name_or_note_keeps_paging_and_matra(self):
        from django.contrib.auth.models import User
        from django.urls import reverse
        from accounts.models import Satuan
        User.objects.create_superuser(username="root_cari", password="rahasia-123")
        self.client.login(username="root_cari", password="rahasia-123")
        Satuan.objects.all().delete()
        for i in range(20):
            Satuan.objects.create(nama=f"KODIM {i:04d}/UJI", matra="darat")
        Satuan.objects.create(nama="KOREM 011/LW", matra="darat", keterangan="Lhokseumawe")
        Satuan.objects.create(nama="LANTAMAL KODIM-MIRIP", matra="laut")
        url = reverse("accounts:pengaturan")

        def nama(**query):
            response = self.client.get(url, {"tab": "satuan", **query})
            return response, [s.nama for s in response.context["satuan_list"]]

        response, hasil = nama(cari_satuan="korem")
        self.assertEqual(hasil, ["KOREM 011/LW"])
        self.assertContains(response, 'name="cari_satuan" value="korem"')
        self.assertEqual(nama(cari_satuan="lhokseumawe")[1], ["KOREM 011/LW"])  # by note
        self.assertEqual(nama(cari_satuan="tidak-ada")[1], [])
        self.assertContains(nama(cari_satuan="tidak-ada")[0], "Tidak ada satuan yang cocok.")
        # Only the matra shown is searched, and paging carries the search on.
        response, hasil = nama(cari_satuan="kodim")
        self.assertEqual(response.context["satuan_list"].paginator.count, 20)
        self.assertRegex(response.content.decode(), r'href="[^"]*cari_satuan=kodim[^"]*hal_satuan=2"')
        self.assertEqual(nama(cari_satuan="kodim", hal_satuan="2")[1][0], "KODIM 0015/UJI")
        self.assertEqual(nama(cari_satuan="kodim", matra="laut")[1], ["LANTAMAL KODIM-MIRIP"])
        self.assertEqual(self.client.get(url, {"tab": "satuan"}).context["satuan_list"].paginator.count, 21)
