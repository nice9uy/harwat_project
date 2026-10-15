from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import AkunPublik, Anggota


def _akun(username, grup=None, matra=""):
    user = User.objects.create_user(username=username, password="rahasia-123")
    if grup:
        user.groups.add(Group.objects.get(name=grup))
    AkunPublik.objects.filter(user=user).update(matra=matra)
    return user


class AktivasiKetuaTimTests(TestCase):
    def setUp(self):
        self.admin_darat = _akun("admin_darat", "Admin", "darat")
        self.k_darat = _akun("k_darat", "Ketua Tim", "darat")
        self.k_laut = _akun("k_laut", "Ketua Tim", "laut")
        Anggota.add_root(user=self.k_darat, admin=self.admin_darat)
        Anggota.add_root(user=self.k_laut)

    def test_admin_sees_and_switches_only_their_matra(self):
        self.client.login(username="admin_darat", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:aktivasi_ketua_tim"))
        self.assertContains(halaman, "Aktivasi Ketua Tim")
        self.assertEqual([a.username for a in halaman.context["daftar"]], ["k_darat"])
        ubah = reverse("accounts:aktivasi_ketua_tim_ubah", args=[self.k_darat.publik.uuid])
        self.client.post(ubah)
        self.k_darat.refresh_from_db()
        self.assertFalse(self.k_darat.is_active)
        lain = reverse("accounts:aktivasi_ketua_tim_ubah", args=[self.k_laut.publik.uuid])
        self.assertEqual(self.client.post(lain).status_code, 403)
        self.k_laut.refresh_from_db()
        self.assertTrue(self.k_laut.is_active)
        # Only Ketua Tim are switched here.
        self.assertEqual(self.client.post(reverse("accounts:aktivasi_ketua_tim_ubah", args=[self.admin_darat.publik.uuid])).status_code, 403)

    def test_superuser_sees_every_matra(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:aktivasi_ketua_tim"))
        self.assertEqual([a.username for a in halaman.context["daftar"]], ["k_darat", "k_laut"])
        halaman = self.client.get(reverse("accounts:aktivasi_ketua_tim") + "?matra=laut")
        self.assertEqual([a.username for a in halaman.context["daftar"]], ["k_laut"])
        self.client.post(reverse("accounts:aktivasi_ketua_tim_ubah", args=[self.k_laut.publik.uuid]))
        self.k_laut.refresh_from_db()
        self.assertFalse(self.k_laut.is_active)

    def test_other_roles_neither_see_the_menu_nor_open_it(self):
        _akun("pimpinan", "Pimpinan")
        for username in ("k_darat", "pimpinan"):
            self.client.login(username=username, password="rahasia-123")
            self.assertNotIn("aktivasi_ketua_tim", self.client.get(reverse("accounts:info_profile")).context["menu_boleh"])
            self.assertNotEqual(self.client.get(reverse("accounts:aktivasi_ketua_tim")).status_code, 200)
