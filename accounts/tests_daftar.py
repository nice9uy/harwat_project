import io

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from accounts import daftar
from accounts.models import AkunPublik, Anggota, Laporan, Satuan


def _foto():
    berkas = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(berkas, "JPEG")
    return SimpleUploadedFile("foto.jpg", berkas.getvalue(), content_type="image/jpeg")


class DaftarKetuaTimTests(TestCase):
    def setUp(self):
        self.satuan = Satuan.objects.create(nama="KODAM JAYA", matra="darat")
        Satuan.objects.create(nama="LANTAMAL", matra="laut")
        self.url = reverse("accounts:daftar_form") + "?matra=darat"

    def _data(self, **lain):
        data = {
            "daftar-username": "ketua.baru", "daftar-password1": "12345",
            "daftar-tipe_identitas": "TNI", "daftar-nip": "123", "daftar-nama": "budi", "daftar-pangkat": "kapten",
            "daftar-jabatan": "teknisi", "daftar-satuan": self.satuan.pk, "daftar-foto": _foto(),
        }
        data.update(lain)
        return data

    def test_login_page_links_to_the_matra_modal(self):
        login = self.client.get(reverse("accounts:login"))
        self.assertContains(login, "Daftar sebagai Ketua Tim")
        # The login form's hx-select would otherwise empty the modal it opens.
        self.assertContains(login, 'hx-disinherit="hx-select"')
        self.assertContains(self.client.get(reverse("accounts:daftar_matra")), "Matra Laut")
        form = self.client.get(self.url)
        self.assertContains(form, "KODAM JAYA")
        self.assertContains(form, 'value="12345"')
        self.assertNotContains(form, "Ulangi kata sandi")
        self.assertNotContains(form, "LANTAMAL")

    def test_sign_up_waits_for_the_admin_of_that_matra(self):
        selesai = self.client.post(self.url, self._data())
        self.assertContains(selesai, "Pendaftaran Terkirim")
        user = User.objects.get(username="ketua.baru")
        self.assertFalse(user.is_active)
        self.assertEqual(user.groups.get().name, "Ketua Tim")
        self.assertEqual((user.publik.matra, user.publik.satuan), ("darat", self.satuan))
        self.assertEqual(Laporan.objects.get(akun=user).nama, "BUDI")
        node = Anggota.objects.get(user=user)
        self.assertTrue(node.is_root())
        # Not yet: told so on the login page.
        login = self.client.post(reverse("accounts:login"), {"username": "ketua.baru", "password": "12345"})
        self.assertContains(login, "belum diaktifkan")
        # The Admin of Matra Darat sees and switches them on, and gets them as their Ketua Tim.
        admin = User.objects.create_user(username="admin_darat", password="rahasia-123")
        admin.groups.add(Group.objects.get(name="Admin"))
        AkunPublik.objects.filter(user=admin).update(matra="darat")
        self.client.login(username="admin_darat", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:aktivasi_ketua_tim"))
        self.assertContains(halaman, "Menunggu aktivasi")
        self.client.post(reverse("accounts:aktivasi_ketua_tim_ubah", args=[user.publik.uuid]))
        user.refresh_from_db()
        node.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(node.admin, admin)
        self.client.logout()
        self.assertTrue(self.client.login(username="ketua.baru", password="12345"))

    def test_bad_input_and_taken_username_are_refused(self):
        User.objects.create_user(username="Ketua.Baru", password="x")
        hasil = self.client.post(self.url, self._data(**{"daftar-password2": "lain"}))
        self.assertContains(hasil, "sudah dipakai")
        self.assertEqual(User.objects.filter(username__iexact="ketua.baru").count(), 1)

    def test_closed_while_too_many_wait(self):
        grup = Group.objects.get(name="Ketua Tim")
        for i in range(daftar.BATAS_MENUNGGU):
            User.objects.create_user(username=f"t{i}", password="x", is_active=False).groups.add(grup)
        self.assertContains(self.client.post(self.url, self._data()), "ditutup")
        self.assertFalse(User.objects.filter(username="ketua.baru").exists())
