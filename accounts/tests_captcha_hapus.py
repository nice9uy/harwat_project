"""Every delete asks for the code its dialog shows (accounts/captcha_hapus.py)."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Satuan
from fleet.models import Vehicle


class CaptchaHapusTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")

    def _kode(self, nama):
        return self.client.session[f"captcha_hapus:{nama}"]

    def test_vehicle_needs_the_code_shown(self):
        v = Vehicle.objects.create(nopol="B 77 CP", merek="Uji", group_kendaraan="B")
        dialog = self.client.get(reverse("fleet:vehicle_delete_confirm", args=[v.uuid]))
        kode = self._kode(f"kendaraan:{v.uuid}")
        self.assertContains(dialog, kode)
        self.assertContains(dialog, "Masukkan kode di atas")
        url = reverse("fleet:vehicle_delete", args=[v.uuid])
        self.client.post(url, {"captcha": "000000" if kode != "000000" else "111111"})
        self.assertTrue(Vehicle.objects.filter(pk=v.pk).exists())  # wrong code: kept
        self.client.post(url, {"captcha": kode})
        self.assertTrue(Vehicle.objects.filter(pk=v.pk).exists())  # a code is used up once tried
        self.client.get(reverse("fleet:vehicle_delete_confirm", args=[v.uuid]))
        self.client.post(url, {"captcha": self._kode(f"kendaraan:{v.uuid}")})
        self.assertFalse(Vehicle.objects.filter(pk=v.pk).exists())

    def test_satuan_without_a_code_is_kept(self):
        s = Satuan.objects.create(nama="Satuan Uji")
        self.client.post(reverse("accounts:satuan_delete", args=[s.uuid]))
        self.assertTrue(Satuan.objects.filter(pk=s.pk).exists())
        self.client.get(reverse("accounts:satuan_delete", args=[s.uuid]))
        self.client.post(reverse("accounts:satuan_delete", args=[s.uuid]), {"captcha": self._kode(f"satuan:{s.uuid}")})
        self.assertFalse(Satuan.objects.filter(pk=s.pk).exists())
