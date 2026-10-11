"""Backup menu: superusers make, list, download and delete backups."""
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from accounts import backup
from fleet.models import Vehicle


class BackupTests(TransactionTestCase):
    # Not a TestCase: SQLite can't copy a database from inside the transaction
    # TestCase wraps each test in (the copy would wait on it forever). Requests
    # in the app run outside one. The database is emptied after each test,
    # migration rows included, so the role group is made here when needed.

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        media = Path(self.tmp.name) / "media"
        (media / "kendaraan").mkdir(parents=True)
        (media / "kendaraan" / "a.jpg").write_bytes(b"foto")
        override = override_settings(BACKUP_DIR=Path(self.tmp.name) / "backup", MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:backup")

    def _akhiran(self):
        return "sqlite3" if connection.vendor == "sqlite" else "json"

    def test_superuser_only(self):
        self.assertContains(self.client.get(self.url), f'<a href="{self.url}" class=')
        self.assertContains(self.client.get(self.url), "Belum ada backup.")
        admin = User.objects.create_user(username="pusat", password="rahasia-123")
        admin.groups.add(Group.objects.get_or_create(name="Admin")[0])
        self.client.login(username="pusat", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:dashboard")), f'href="{self.url}"')
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        self.client.post(reverse("accounts:backup_buat"), {"jenis": "database"})
        self.assertEqual(backup.daftar(), [])

    def test_database_backup_is_a_readable_copy(self):
        Vehicle.objects.create(nopol="B 1 BK", merek="Uji")
        self.assertRedirects(self.client.post(reverse("accounts:backup_buat"), {"jenis": "database"}), self.url)
        (b,) = backup.daftar()
        # A SQLite file on SQLite, a JSON dump on any other engine (PostgreSQL in production).
        self.assertRegex(b["nama"], rf"^backup-\d{{8}}-\d{{6}}-database\.{self._akhiran()}$")
        halaman = self.client.get(self.url)
        self.assertContains(halaman, b["nama"])
        unduh = self.client.get(reverse("accounts:backup_unduh", args=[b["nama"]]))
        self.assertIn(b["nama"], unduh["Content-Disposition"])
        isi = b"".join(unduh.streaming_content)
        if connection.vendor != "sqlite":
            import json
            kendaraan = [r for r in json.loads(isi) if r["model"] == "fleet.vehicle"]
            self.assertEqual([r["fields"]["nopol"] for r in kendaraan], ["B 1 BK"])
            return
        salinan = Path(self.tmp.name) / "cek.sqlite3"
        salinan.write_bytes(isi)
        db = sqlite3.connect(salinan)
        self.assertEqual(db.execute("select nopol from fleet_vehicle").fetchall(), [("B 1 BK",)])
        db.close()

    def test_full_backup_zips_database_and_photos(self):
        self.client.post(reverse("accounts:backup_buat"), {"jenis": "lengkap"})
        (b,) = backup.daftar()
        self.assertTrue(b["nama"].endswith("-lengkap.zip"))
        with zipfile.ZipFile(Path(self.tmp.name) / "backup" / b["nama"]) as z:
            self.assertEqual(sorted(z.namelist()), [f"database.{self._akhiran()}", "media/kendaraan/a.jpg"])
            self.assertEqual(z.read("media/kendaraan/a.jpg"), b"foto")

    def test_delete_and_only_backup_names_are_served(self):
        self.client.post(reverse("accounts:backup_buat"), {"jenis": "database"})
        nama = backup.daftar()[0]["nama"]
        hapus = reverse("accounts:backup_hapus", args=[nama])
        self.assertContains(self.client.get(hapus), "Yakin ingin menghapus backup")
        self.assertRedirects(self.client.post(hapus), self.url)
        self.assertEqual(backup.daftar(), [])
        # Anything else in or near the folder is not a backup.
        (Path(self.tmp.name) / "backup" / "rahasia.txt").write_text("x")
        for nama in ("rahasia.txt", "..%2Fmedia%2Fkendaraan%2Fa.jpg", "backup-20260101-000000-database.sqlite3"):
            self.assertEqual(self.client.get(f"/backup/{nama}/unduh/").status_code, 404, nama)
        self.assertEqual(self.client.post(reverse("accounts:backup_buat"), {"jenis": "zzz"}).status_code, 404)
