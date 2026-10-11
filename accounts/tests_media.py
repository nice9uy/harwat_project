"""Uploaded photos: served from the storage through /media/ to signed-in users,
and carried over from an old media folder by `manage.py impor_media`."""
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse


class MediaTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media = Path(self.tmp.name) / "media"
        (self.media / "kendaraan").mkdir(parents=True)
        (self.media / "kendaraan" / "a b.jpg").write_bytes(b"isi foto")
        (Path(self.tmp.name) / "rahasia.txt").write_text("jangan")
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        User.objects.create_user(username="u", password="rahasia-123")

    def test_signed_in_users_only(self):
        url = reverse("media", args=["kendaraan/a b.jpg"])
        self.assertEqual(self.client.get(url).status_code, 302)  # to the login page
        self.client.login(username="u", password="rahasia-123")
        response = self.client.get(url)
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/jpeg"))
        self.assertEqual(b"".join(response.streaming_content), b"isi foto")
        self.assertIn("private", response["Cache-Control"])

    def test_missing_files_and_paths_outside_the_storage_are_404(self):
        self.client.login(username="u", password="rahasia-123")
        for nama in ("kendaraan/tidak-ada.jpg", "../rahasia.txt", "kendaraan/../../rahasia.txt", "kendaraan"):
            self.assertEqual(self.client.get(f"/media/{nama}").status_code, 404, nama)

    def test_impor_media_copies_a_folder_once_keeping_paths(self):
        lama = Path(self.tmp.name) / "lama"
        (lama / "pemeriksaan").mkdir(parents=True)
        (lama / "pemeriksaan" / "x.jpg").write_bytes(b"x")
        (lama / "kendaraan").mkdir()
        (lama / "kendaraan" / "a b.jpg").write_bytes(b"versi lama")  # already in the storage
        keluar = StringIO()
        call_command("impor_media", str(lama), stdout=keluar)
        self.assertIn("1 file disalin, 1 sudah ada", keluar.getvalue())
        self.assertEqual(default_storage.open("pemeriksaan/x.jpg").read(), b"x")
        self.assertEqual(default_storage.open("kendaraan/a b.jpg").read(), b"isi foto")  # not overwritten
        keluar = StringIO()
        call_command("impor_media", str(lama), stdout=keluar)
        self.assertIn("0 file disalin, 2 sudah ada", keluar.getvalue())
