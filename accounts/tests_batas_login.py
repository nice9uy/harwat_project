from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts import batas_login
from accounts.models import GagalLogin


class BatasLoginTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="budi", password="rahasia-123")
        self.url = reverse("accounts:login")

    def _login(self, password, ip="10.0.0.1", username="budi"):
        return self.client.post(self.url, {"username": username, "password": password}, HTTP_X_REAL_IP=ip)

    def test_username_locked_after_wrong_passwords(self):
        for _ in range(batas_login.BATAS_USERNAME):
            self.assertContains(self._login("salah"), "salah")
        # Locked: even the right password is refused, without being checked.
        terkunci = self._login("rahasia-123")
        self.assertContains(terkunci, "Terlalu banyak percobaan")
        self.assertNotIn("_auth_user_id", self.client.session)
        # The lock ends.
        GagalLogin.objects.update(terkunci_sampai=None)
        self.assertEqual(self._login("rahasia-123").status_code, 302)
        self.assertFalse(GagalLogin.objects.filter(kunci="u:budi").exists())

    def test_ip_locked_across_usernames(self):
        for i in range(batas_login.BATAS_IP):
            self._login("salah", username=f"orang{i}")
        self.assertContains(self._login("rahasia-123"), "Terlalu banyak percobaan")
        # Another IP still logs in.
        self.assertEqual(self._login("rahasia-123", ip="10.0.0.2").status_code, 302)


class WajibGantiPasswordTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="12345")

    def test_default_password_must_be_changed_first(self):
        self.client.post(reverse("accounts:login"), {"username": "root", "password": "12345"})
        self.assertRedirects(self.client.get(reverse("accounts:pengaturan")), reverse("accounts:ganti_password"))
        self.assertEqual(self.client.get(reverse("accounts:dashboard_partial"), HTTP_HX_REQUEST="true")["HX-Redirect"],
                         reverse("accounts:ganti_password"))
        self.assertEqual(self.client.get(reverse("accounts:ganti_password")).status_code, 200)
        # Not to the default again.
        sama = self.client.post(reverse("accounts:ganti_password"), {
            "old_password": "12345", "new_password1": "12345", "new_password2": "12345",
        })
        self.assertContains(sama, "tidak boleh sama dengan password bawaan")
        self.client.post(reverse("accounts:ganti_password"), {
            "old_password": "12345", "new_password1": "baru", "new_password2": "baru",
        })
        self.assertEqual(self.client.get(reverse("accounts:pengaturan")).status_code, 200)

    def test_other_passwords_go_straight_in(self):
        User.objects.create_superuser(username="lain", password="bukan-bawaan")
        self.client.post(reverse("accounts:login"), {"username": "lain", "password": "bukan-bawaan"})
        self.assertEqual(self.client.get(reverse("accounts:pengaturan")).status_code, 200)
