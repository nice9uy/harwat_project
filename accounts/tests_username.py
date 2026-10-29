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
