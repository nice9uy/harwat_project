"""Usernames are unique whatever their case, on the forms and in the database."""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts import roles
from accounts.forms import DaftarKetuaForm, UserCreateForm


class UsernameUnikTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="ketua", password="rahasia-123")

    def test_tambah_user_refuses_the_same_name_in_other_case(self):
        for nama in ("ketua", "KETUA", " Ketua "):
            form = UserCreateForm({"username": nama, "keanggotaan": "pimpinan"}, kode_pengelola=roles.SUPERUSER)
            self.assertFalse(form.is_valid(), nama)
            self.assertIn("Nama pengguna ini sudah dipakai.", form.errors["username"], nama)

    def test_daftar_ketua_tim_refuses_it_too(self):
        form = DaftarKetuaForm({"username": "KeTua", "password1": "12345"})
        self.assertFalse(form.is_valid())
        self.assertIn("Nama pengguna ini sudah dipakai.", form.errors["username"])

    def test_the_database_refuses_it(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="KETUA", password="x")
        User.objects.create_user(username="ketua2", password="x")


class NamaDipakaiModalTests(TestCase):
    """A name already taken comes back with a dialog saying so, not only the field's error."""

    def setUp(self):
        User.objects.create_user(username="ketua", password="rahasia-123")

    def test_daftar_shows_the_dialog(self):
        from django.urls import reverse

        response = self.client.post(reverse("accounts:daftar_form") + "?matra=darat", {"daftar-username": "KETUA"})
        self.assertContains(response, "Nama pengguna sudah ada")
        self.assertContains(response, "Silakan gunakan nama pengguna yang lain.")
        # A free name: no dialog.
        bebas = self.client.post(reverse("accounts:daftar_form") + "?matra=darat", {"daftar-username": "bebas"})
        self.assertNotContains(bebas, "Nama pengguna sudah ada")


class DaftarDibatasiTests(TestCase):
    """The public Daftar form tells whether a name is taken: sends are capped per IP."""

    def test_after_the_cap_nothing_is_checked(self):
        from django.urls import reverse

        from accounts import batas_login

        User.objects.create_user(username="ketua", password="rahasia-123")
        url = reverse("accounts:daftar_form") + "?matra=darat"
        for _ in range(batas_login.BATAS_DAFTAR):
            self.client.post(url, {"daftar-username": "bebas"})
        terkunci = self.client.post(url, {"daftar-username": "ketua"})
        self.assertContains(terkunci, "Terlalu banyak percobaan pendaftaran")
        self.assertNotContains(terkunci, "Nama pengguna sudah ada")
        self.assertNotContains(terkunci, "sudah dipakai")
        self.assertContains(terkunci, 'value="ketua"')  # what was typed stays
        # Another address is not held up.
        lain = self.client.post(url, {"daftar-username": "ketua"}, REMOTE_ADDR="10.9.9.9")
        self.assertContains(lain, "Nama pengguna sudah ada")


class AkunBelumAktifModalTests(TestCase):
    """The right password on a switched-off account: a dialog says why, not a line of text."""

    def _masuk(self, password):
        from django.urls import reverse

        return self.client.post(reverse("accounts:login"), {"username": "calon", "password": password})

    def test_waiting_for_activation(self):
        User.objects.create_user(username="calon", password="rahasia-123", is_active=False)
        respon = self._masuk("rahasia-123")
        self.assertContains(respon, "Akun belum diaktifkan")
        self.assertContains(respon, 'role="alertdialog"')
        # A wrong password tells nothing about the account.
        salah = self._masuk("salah-salah")
        self.assertNotContains(salah, "Akun belum diaktifkan")
        self.assertContains(salah, "Nama pengguna atau kata sandi salah")

    def test_switched_off_later(self):
        from django.utils import timezone

        User.objects.create_user(username="calon", password="rahasia-123", is_active=False, last_login=timezone.now())
        self.assertContains(self._masuk("rahasia-123"), "Akun dinonaktifkan")
