"""Form Group: a superuser sets which Form Tambah forms each Ketua Tim's team,
and each Tim Penambahan Data member in it, may open."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts import roles
from accounts.models import AksesFormTambah, Anggota


class FormGroupTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:form_group")
        self.ketua_user = User.objects.create_user(username="ketua1", password="rahasia-123")
        self.ketua_user.groups.add(Group.objects.get(name="Ketua Tim"))
        self.ketua = Anggota.add_root(user=self.ketua_user)
        self.penambah = self._anggota("penambah1", "Tim Penambahan Data")
        self.pemeriksa = self._anggota("pemeriksa1", "Tim Pemeriksaan")

    def _anggota(self, username, group):
        user = User.objects.create_user(username=username, password="rahasia-123")
        user.groups.add(Group.objects.get(name=group))
        Anggota.objects.get(pk=self.ketua.pk).add_child(user=user)
        return user

    def _url(self, nama, user):
        return reverse(f"accounts:form_group_{nama}", args=[user.publik.uuid])

    def _form(self, user):
        return roles.form_tambah_boleh(user)

    def test_table_has_form_and_aksi_columns(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'href="{self.url}"')
        for kolom in ("Ketua Tim / Anggota", "Form Tambah", "Aksi"):
            self.assertContains(response, f'<th class="py-2 px-4 font-medium">{kolom}</th>', html=True)
        content = response.content.decode()
        self.assertLess(content.index("ketua1"), content.index("penambah1"))
        self.assertNotContains(response, "pemeriksa1")
        self.assertContains(response, self._url("tambah", self.penambah))
        self.assertContains(response, self._url("hapus", self.penambah))
        # Everything is allowed at first, so there is nothing left to add.
        self.assertContains(self.client.get(self._url("tambah", self.penambah)), "Semua form sudah dimiliki")
        self.assertContains(response, self._url("lihat", self.ketua_user))

    def test_others_get_no_menu_and_no_page(self):
        admin = User.objects.create_user(username="pusat", password="rahasia-123")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client.login(username="pusat", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:dashboard")), f'href="{self.url}"')
        for url in (self.url, self._url("tambah", self.penambah), self._url("hapus", self.penambah)):
            self.assertNotEqual(self.client.get(url).status_code, 200)
        self.client.post(self._url("hapus", self.penambah), {"kode": "B"})
        self.assertFalse(AksesFormTambah.objects.exists())

    def test_hapus_then_tambah_on_a_member(self):
        modal = self.client.get(self._url("hapus", self.penambah))
        self.assertContains(modal, "Hapus Form")
        self.assertContains(modal, f'hx-get="{self._url("hapus", self.penambah)}?kode=diesel"')
        konfirmasi = self.client.get(self._url("hapus", self.penambah), {"kode": "diesel"})
        self.assertContains(konfirmasi, "Yakin ingin menghapus form")
        self.assertContains(konfirmasi, 'name="kode" value="diesel"')
        self.assertEqual(self._form(self.penambah), [kode for kode, _ in roles.FORM_TAMBAH])
        response = self.client.post(self._url("hapus", self.penambah), {"kode": "diesel"})
        self.assertEqual(response["HX-Redirect"], self.url)
        self.client.post(self._url("hapus", self.penambah), {"kode": "B"})
        self.assertEqual(self._form(self.penambah), ["bermotor", "jeep", "ranpur", "rantis", "non_kendaraan"])

        modal = self.client.get(self._url("tambah", self.penambah))
        self.assertContains(modal, "Tambah Form")
        self.assertContains(modal, 'name="kode" value="B"\n')
        self.assertContains(modal, 'name="kode" value="bermotor" checked disabled')
        self.assertContains(self.client.post(self._url("tambah", self.penambah), {}), "Pilih minimal satu form.")
        self.client.post(self._url("tambah", self.penambah), {"kode": ["B"]})
        self.assertEqual(self._form(self.penambah), ["B", "bermotor", "jeep", "ranpur", "rantis", "non_kendaraan"])
        lihat = self.client.get(self._url("lihat", self.penambah))
        self.assertContains(lihat, "Motor")
        self.assertNotContains(lihat, "Kendaraan Diesel")

    def test_ketua_row_applies_to_the_team(self):
        self.client.post(self._url("hapus", self.ketua_user), {"kode": "diesel"})
        self.assertNotIn("diesel", self._form(self.penambah))
        # A member added later starts from the Ketua Tim's forms.
        baru = self._anggota("penambah2", "Tim Penambahan Data")
        self.assertEqual(self._form(baru), ["B", "bermotor", "jeep", "ranpur", "rantis", "non_kendaraan"])
        # Only Tim Penambahan Data members get a row of their own.
        self.assertFalse(AksesFormTambah.objects.filter(user=self.pemeriksa).exists())
        self.client.post(self._url("tambah", self.ketua_user), {"kode": ["diesel"]})
        self.assertIn("diesel", self._form(self.penambah))

    def test_only_ketua_and_tim_penambahan_data_rows(self):
        self.assertEqual(self.client.get(self._url("hapus", self.pemeriksa)).status_code, 404)

    def test_forms_limit_form_tambah(self):
        for kode in ("B", "diesel"):
            self.client.post(self._url("hapus", self.penambah), {"kode": kode})
        self.client.login(username="penambah1", password="rahasia-123")
        response = self.client.get(reverse("accounts:form_tambah"))
        self.assertContains(response, 'name="golongan" value="bermotor"')
        self.assertNotContains(response, 'name="golongan" value="B"')
        self.assertNotContains(response, 'name="golongan" value="diesel"')
        buat = reverse("fleet:vehicle_create")
        self.assertEqual(self.client.get(f"{buat}?group=diesel&penambah=1").status_code, 403)
        self.assertEqual(self.client.get(f"{buat}?group=bermotor&penambah=1").status_code, 200)
        # In the modal (HTMX) the refusal is explained and nothing is saved.
        response = self.client.post(
            f"{buat}?group=diesel&penambah=1", {"nopol": "B 1 X", "merek": "Uji"}, HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Anda tidak punya akses ke form Kendaraan Diesel")
        from fleet.models import Vehicle
        self.assertFalse(Vehicle.objects.filter(nopol="B 1 X").exists())

    def test_member_without_setting_opens_every_form(self):
        self.client.login(username="penambah1", password="rahasia-123")
        response = self.client.get(reverse("accounts:form_tambah"))
        for kode in ("B", "bermotor", "diesel"):
            self.assertContains(response, f'name="golongan" value="{kode}"')

    def test_no_form_left(self):
        for kode, _ in roles.FORM_TAMBAH:
            self.client.post(self._url("hapus", self.penambah), {"kode": kode})
        self.assertContains(self.client.get(self.url), "Belum ada form")
        self.client.login(username="penambah1", password="rahasia-123")
        response = self.client.get(reverse("accounts:form_tambah"))
        self.assertContains(response, "Belum ada form yang bisa Anda akses")
        self.assertNotContains(response, 'name="golongan"')
