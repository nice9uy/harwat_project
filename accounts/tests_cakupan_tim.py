"""Team scope: query counts that don't grow with the number of teams, and
Laporan Tim limited to the viewer's own teams."""
from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import AkunPublik, Anggota


def _akun(username, grup, matra="darat"):
    user = User.objects.create_user(username=username, password="x")
    user.groups.add(Group.objects.get(name=grup))
    AkunPublik.objects.filter(user=user).update(matra=matra)
    return user


class CakupanTimTests(TestCase):
    def setUp(self):
        self.admin = _akun("admin_darat", "Admin")
        self.admin_laut = _akun("admin_laut", "Admin", "laut")

    def _tim(self, n, awal=0, admin=None):
        for i in range(awal, awal + n):
            node = Anggota.add_root(user=_akun(f"ketua{i}", "Ketua Tim"), admin=admin or self.admin)
            Anggota.objects.get(pk=node.pk).add_child(user=_akun(f"tim{i}", "Tim Pemeriksaan"))

    def _hitung(self, url):
        from accounts import keamanan
        keamanan._muat_blokir()  # read once and kept: not part of what a page costs
        keamanan.pemeliharaan()
        with CaptureQueriesContext(connection) as q:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(q)

    def test_pages_do_not_query_per_team(self):
        self.client.force_login(self.admin)
        self._tim(2)
        urls = [reverse(n) for n in ("accounts:anggota_tim", "accounts:status", "accounts:rekap_kerusakan", "accounts:laporan_tim")]
        sedikit = [self._hitung(u) for u in urls]
        self._tim(10, awal=2)
        self.assertEqual([self._hitung(u) for u in urls], sedikit)

    def test_laporan_tim_shows_only_own_teams(self):
        self._tim(1)
        self._tim(1, awal=1, admin=self.admin_laut)
        node_laut = Anggota.objects.get(user__username="ketua1")
        self.client.force_login(self.admin)
        halaman = self.client.get(reverse("accounts:laporan_tim"))
        self.assertContains(halaman, "ketua0")
        self.assertNotContains(halaman, "ketua1")
        self.assertEqual(self.client.get(reverse("accounts:laporan_tim_detail", args=[node_laut.uuid])).status_code, 404)
        # A Ketua Tim: their own team only.
        self.client.force_login(User.objects.get(username="ketua0"))
        self.assertNotContains(self.client.get(reverse("accounts:laporan_tim")), "ketua1")
        self.assertEqual(self.client.get(reverse("accounts:laporan_tim_detail", args=[node_laut.uuid])).status_code, 404)
