"""The Aktivasi Ketua Tim menu shows how many sign-ups wait for activation."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts.aktivasi import jumlah_menunggu
from accounts.models import AkunPublik


class LencanaAktivasiTests(TestCase):
    def _ketua(self, username, matra, aktif=False):
        user = User.objects.create_user(username=username, password="rahasia-123", is_active=aktif)
        user.groups.add(Group.objects.get(name="Ketua Tim"))
        AkunPublik.objects.update_or_create(user=user, defaults={"matra": matra})
        return user

    def setUp(self):
        self._ketua("darat1", "darat")
        self._ketua("darat2", "darat")
        self._ketua("udara1", "udara")
        self._ketua("sudah", "darat", aktif=True)
        self.admin = User.objects.create_user(username="admin_darat", password="rahasia-123")
        self.admin.groups.add(Group.objects.get(name="Admin"))
        AkunPublik.objects.update_or_create(user=self.admin, defaults={"matra": "darat"})

    def test_counts_per_viewer(self):
        self.assertEqual(jumlah_menunggu(User.objects.get(pk=self.admin.pk)), 2)
        self.assertEqual(jumlah_menunggu(User.objects.create_superuser(username="root", password="x")), 3)
        self.assertEqual(jumlah_menunggu(User.objects.create_user(username="biasa", password="x")), 0)

    def test_badge_on_the_menu(self):
        self.client.login(username="admin_darat", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:aktivasi_ketua_tim"))
        self.assertContains(halaman, 'aria-label="2 pendaftar menunggu aktivasi"', count=2)  # sidebar and phone Menu
        User.objects.filter(username__in=["darat1", "darat2"]).update(is_active=True)
        self.assertNotContains(self.client.get(reverse("accounts:aktivasi_ketua_tim")), "menunggu aktivasi\"")
