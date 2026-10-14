"""Backup menu: superusers make, list, download, upload, delete and restore backups."""
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

    def test_one_button_backs_up_everything(self):
        halaman = self.client.get(self.url)
        self.assertContains(halaman, "Buat Backup")
        for lama in ("Backup Database + Foto", 'name="jenis"'):
            self.assertNotContains(halaman, lama)
        self.client.post(reverse("accounts:backup_buat"))
        (b,) = backup.daftar()
        self.assertTrue(b["nama"].endswith("-lengkap.zip"))
        # Two within one second get names of their own.
        self.client.post(reverse("accounts:backup_buat"))
        self.assertEqual(len({b["nama"] for b in backup.daftar()}), 2)

    def test_restore_puts_data_and_photos_back(self):
        foto = Path(self.tmp.name) / "media" / "kendaraan" / "a.jpg"
        lama = Vehicle.objects.create(nopol="B 1 PL", merek="Lama")
        self.client.post(reverse("accounts:backup_buat"))
        nama = backup.daftar()[0]["nama"]
        # Things change after the backup.
        lama.delete()
        Vehicle.objects.create(nopol="B 2 PL", merek="Baru")
        foto.write_bytes(b"foto yang berubah")
        pulihkan = reverse("accounts:backup_pulihkan", args=[nama])
        modal = self.client.get(pulihkan)
        for teks in ("Pulihkan dari Backup", backup.KATA_PULIHKAN, "akan hilang"):
            self.assertContains(modal, teks)
        # Without the word typed nothing happens.
        self.assertRedirects(self.client.post(pulihkan, {"konfirmasi": "ya"}), self.url)
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 2 PL"])
        self.assertEqual(len(backup.daftar()), 1)
        self.client.post(pulihkan, {"konfirmasi": "pulihkan"})
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 1 PL"])
        self.assertEqual(foto.read_bytes(), b"foto")
        # The state before the restore was backed up first: restoring that undoes it.
        semua = backup.daftar()
        self.assertEqual(len(semua), 2)
        pengaman = next(b["nama"] for b in semua if b["nama"] != nama)
        with zipfile.ZipFile(Path(self.tmp.name) / "backup" / pengaman) as z:
            self.assertEqual(z.read("media/kendaraan/a.jpg"), b"foto yang berubah")
        backup.pulihkan(Path(self.tmp.name) / "backup" / pengaman)
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 2 PL"])
        self.assertEqual(foto.read_bytes(), b"foto yang berubah")
        # Still signed in, and only a superuser restores.
        self.assertEqual(self.client.get(self.url).status_code, 200)
        User.objects.create_user(username="biasa", password="rahasia-123")
        self.client.login(username="biasa", password="rahasia-123")
        self.assertNotEqual(self.client.post(pulihkan, {"konfirmasi": backup.KATA_PULIHKAN}).status_code, 200)
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 2 PL"])

    def test_restore_from_a_json_dump(self):
        # What production (PostgreSQL) backs up: a JSON dump inside the zip.
        from django.core.management import call_command
        Vehicle.objects.create(nopol="B 3 PL", merek="Json")
        Group.objects.get_or_create(name="Admin")
        folder = Path(self.tmp.name) / "backup"
        folder.mkdir(parents=True, exist_ok=True)
        dump = folder / "database.json"
        with open(dump, "w", encoding="utf-8") as f:
            call_command("dumpdata", "--natural-foreign", "--exclude", "contenttypes", "--exclude", "sessions", stdout=f)
        arsip = folder / "backup-20260101-000000-lengkap.zip"
        with zipfile.ZipFile(arsip, "w") as z:
            z.write(dump, "database.json")
            z.writestr("media/kendaraan/b.jpg", b"foto json")
            z.writestr("media/../luar.txt", b"jangan")  # never leaves the media folder
        dump.unlink()
        Vehicle.objects.all().delete()
        Vehicle.objects.create(nopol="B 4 PL", merek="Sesudah")
        User.objects.create_user(username="sesudah", password="x")
        self.assertEqual(backup.pulihkan(arsip), 1)
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 3 PL"])
        self.assertEqual(sorted(User.objects.values_list("username", flat=True)), ["root"])
        self.assertTrue(Group.objects.filter(name="Admin").exists())
        self.assertEqual((Path(self.tmp.name) / "media" / "kendaraan" / "b.jpg").read_bytes(), b"foto json")
        self.assertFalse((Path(self.tmp.name) / "luar.txt").exists())
        # A dump that does not load changes nothing.
        rusak = folder / "backup-20260102-000000-lengkap.zip"
        with zipfile.ZipFile(rusak, "w") as z:
            z.writestr("database.json", '[{"model": "fleet.vehicle", "pk": 1, "fields": {"nopol": null}}]')
        with self.assertRaises(Exception):
            backup.pulihkan(rusak)
        self.assertEqual(list(Vehicle.objects.values_list("nopol", flat=True)), ["B 3 PL"])

    def test_upload_adds_a_backup_to_the_list(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.post(reverse("accounts:backup_buat"))
        nama = backup.daftar()[0]["nama"]
        isi = (Path(self.tmp.name) / "backup" / nama).read_bytes()
        unggah = reverse("accounts:backup_unggah")
        self.assertRedirects(self.client.post(unggah, {"berkas": SimpleUploadedFile("dari-server-lain.zip", isi)}), self.url)
        self.assertEqual(len(backup.daftar()), 2)
        # Not a backup: refused and not kept.
        bukan = BytesIO()
        with zipfile.ZipFile(bukan, "w") as z:
            z.writestr("catatan.txt", "x")
        for berkas in (SimpleUploadedFile("x.zip", bukan.getvalue()), SimpleUploadedFile("x.zip", b"bukan zip")):
            self.client.post(unggah, {"berkas": berkas})
        self.client.post(unggah)
        self.assertEqual(len(backup.daftar()), 2)
        self.assertEqual(len(list((Path(self.tmp.name) / "backup").iterdir())), 2)
