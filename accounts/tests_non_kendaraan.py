"""Non Kendaraan menu: a table of inventory items with add, edit, delete, search and paging."""
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from fleet.models import NonKendaraan

import tempfile
from accounts.tests_bantu import kode_hapus


def _foto():
    data = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(data, "PNG")
    return SimpleUploadedFile("foto.png", data.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class NonKendaraanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:non_kendaraan")

    def _data(self, **ganti):
        return {"nama_barang": "Tenda Peleton", "merek": "Eiger", "no_seri": "SN-1", **ganti}

    def test_tenda_table_columns_and_empty_state(self):
        response = self.client.get(self.url)
        for kolom in ("No", "Nama Barang", "Merk/Type", "No. Seri", "Foto", "Aksi"):
            self.assertContains(response, f">{kolom}</th>")
        # The Tenda tab has no Kode Barang, Jumlah, Satuan or Kondisi.
        for kolom in ("Kode Barang", "Jumlah", "Satuan", "Kondisi"):
            self.assertNotContains(response, f">{kolom}</th>")
        self.assertContains(response, "Belum ada data tenda.")
        self.assertContains(response, f'hx-get="{reverse("accounts:non_kendaraan_create")}?group=tenda"')
        # Tabs like the Kendaraan page; Tenda is the first (and default) one.
        self.assertContains(response, f'<a href="{self.url}?group=tenda"')
        self.assertContains(response, "TENDA")
        self.assertContains(response, "+ Tambah\n")

    def test_add_edit_delete(self):
        tambah = reverse("accounts:non_kendaraan_create")
        form = self.client.get(tambah)
        self.assertContains(form, "Tambah Tenda")
        for nama in ("nama_barang", "merek", "no_seri", "foto"):
            self.assertContains(form, f'name="{nama}"')
        for nama in ("kode_barang", "jumlah", "satuan", "kondisi"):
            self.assertNotContains(form, f'name="{nama}"')
        response = self.client.post(tambah, self._data(foto=_foto()), HTTP_HX_REQUEST="true")
        self.assertEqual(response["HX-Redirect"], self.url)
        barang = NonKendaraan.objects.get()
        self.assertEqual(
            (barang.group, barang.nama_barang, barang.kode_barang, barang.ditambahkan_oleh),
            ("tenda", "Tenda Peleton", None, self.user),
        )
        self.assertTrue(barang.foto.name.endswith(".jpg"))  # compressed like every upload
        halaman = self.client.get(self.url)
        for text in ("Tenda Peleton", "Eiger", "SN-1", barang.foto.url):
            self.assertContains(halaman, text)

        ubah = reverse("accounts:non_kendaraan_update", args=[barang.uuid])
        self.assertContains(self.client.get(ubah), "Edit Tenda")
        self.client.post(ubah, self._data(nama_barang="Tenda Regu"))
        barang.refresh_from_db()
        self.assertEqual(barang.nama_barang, "Tenda Regu")
        self.assertTrue(barang.foto)  # kept when no new photo is picked

        hapus = reverse("accounts:non_kendaraan_delete", args=[barang.uuid])
        self.assertContains(self.client.get(hapus), "Yakin ingin menghapus")
        self.assertRedirects(self.client.post(hapus, kode_hapus(self.client, f"non_kendaraan:{barang.uuid}")), self.url)
        self.assertFalse(NonKendaraan.objects.exists())

    def test_several_tenda_without_kode_and_nama_is_required(self):
        tambah = reverse("accounts:non_kendaraan_create")
        self.client.post(tambah, self._data())
        self.client.post(tambah, self._data(nama_barang="Tenda Regu"))
        self.assertEqual(NonKendaraan.objects.count(), 2)
        self.assertEqual(self.client.post(tambah, self._data(nama_barang="")).status_code, 200)
        self.assertEqual(NonKendaraan.objects.count(), 2)

    def test_search_and_paging(self):
        for i in range(17):
            NonKendaraan.objects.create(nama_barang=f"Barang {i:02d}", merek="Hebat" if i == 3 else "Biasa")
        satu = self.client.get(self.url)
        self.assertContains(satu, "Menampilkan 1–15 dari 17 data")
        self.assertContains(satu, "Barang 14")
        self.assertNotContains(satu, "Barang 15")
        self.assertContains(self.client.get(self.url, {"page": 2}), "Barang 16")
        cari = self.client.get(self.url, {"q": "hebat"})
        self.assertContains(cari, "Barang 03")
        self.assertNotContains(cari, "Barang 04")
        self.assertContains(self.client.get(self.url, {"q": "zzz"}), "Tidak ada tenda yang cocok")


class MenuKendaraanTests(TestCase):
    def test_kendaraan_and_non_kendaraan_are_for_superusers_only(self):
        from django.contrib.auth.models import Group
        from accounts.models import Anggota
        for i, group in enumerate(("Admin", "Ketua Tim")):
            user = User.objects.create_user(username=f"u{i}", password="rahasia-123")
            user.groups.add(Group.objects.get(name=group))
            if group == "Ketua Tim":
                Anggota.add_root(user=user)
            self.client.login(username=f"u{i}", password="rahasia-123")
            for nama in ("fleet:vehicle_list", "accounts:non_kendaraan"):
                self.assertEqual(self.client.get(reverse(nama)).status_code, 302, (group, nama))
            home = self.client.get(reverse("accounts:dashboard"))
            for nama in ("fleet:vehicle_list", "accounts:non_kendaraan"):
                self.assertNotContains(home, f'<a href="{reverse(nama)}" class=')
        User.objects.create_superuser(username="su", password="rahasia-123")
        self.client.login(username="su", password="rahasia-123")
        for nama in ("fleet:vehicle_list", "accounts:non_kendaraan"):
            response = self.client.get(reverse(nama))
            self.assertEqual(response.status_code, 200, nama)
            self.assertContains(response, f'<a href="{reverse(nama)}" class=')
