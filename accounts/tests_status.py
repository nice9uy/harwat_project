"""Status menu: a Tim member's unsaved work, and cancelling it."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Anggota, DraftPemeriksaan, PekerjaanAktif
from fleet.models import Vehicle


class StatusTests(TestCase):
    def setUp(self):
        ketua = User.objects.create_user(username="ketua1", password="rahasia-123")
        ketua.groups.add(Group.objects.get(name="Ketua Tim"))
        self.ketua = Anggota.add_root(user=ketua)
        self.vehicle = Vehicle.objects.create(nopol="B 7 ST", merek="Uji", group_kendaraan="bermotor")
        self.url = reverse("accounts:status")
        self.batal = reverse("accounts:status_batal")

    def _login(self, group, username="tim1"):
        user = User.objects.create_user(username=username, password="rahasia-123")
        user.groups.add(Group.objects.get(name=group))
        Anggota.objects.get(pk=self.ketua.pk).add_child(user=user)
        self.client.login(username=username, password="rahasia-123")
        return user

    def test_menu_for_the_three_tim_roles_only(self):
        for i, group in enumerate(("Tim Pemeriksaan", "Tim Penambahan Data", "Tim Perbaikan")):
            self._login(group, f"tim{i}")
            response = self.client.get(self.url)
            self.assertContains(response, f'<a href="{self.url}" class=')
            # Status sits right under History, as a menu of its own.
            content = response.content.decode()
            self.assertLess(content.index("History\n"), content.index(f'<a href="{self.url}" class='))
            self.assertContains(response, "Tidak Aktif")
            self.assertNotContains(response, self.batal)
        self.client.login(username="ketua1", password="rahasia-123")
        self.assertNotEqual(self.client.get(self.url).status_code, 200)
        bos = User.objects.create_user(username="bos", password="rahasia-123")
        bos.groups.add(Group.objects.get(name="Pimpinan"))
        self.client.login(username="bos", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:dashboard")), f'href="{self.url}"')

    def test_superuser_sees_every_tim_member(self):
        aktif = self._login("Tim Perbaikan", "sibuk")
        PekerjaanAktif.objects.create(user=aktif, jenis="perbaikan", vehicle=self.vehicle)
        lain = User.objects.create_user(username="ketualain", password="x")
        lain.groups.add(Group.objects.get(name="Ketua Tim"))
        orang = User.objects.create_user(username="oranglain", password="x")
        orang.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
        Anggota.add_root(user=lain).add_child(user=orang)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertContains(self.client.get(reverse("accounts:dashboard")), f'<a href="{self.url}" class=')
        response = self.client.get(self.url)
        for text in ("1 aktif", "sibuk", "Perbaikan B 7 ST", "oranglain", "Tidak Aktif"):
            self.assertContains(response, text)

    def test_inspection_draft_is_active_and_captcha_cancels_it(self):
        user = self._login("Tim Pemeriksaan")
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=user, data={"a": 1})
        response = self.client.get(self.url)
        self.assertContains(response, "Aktif")
        self.assertNotContains(response, "Tidak Aktif")
        self.assertContains(response, "B 7 ST")
        self.assertContains(response, f'hx-get="{self.batal}"')

        self.assertContains(self.client.get(self.batal), "Masukkan kode di atas")
        self.client.post(self.batal, {"captcha": "salah"})
        self.assertTrue(DraftPemeriksaan.objects.filter(pemeriksa=user).exists())

        self.client.get(self.batal)
        kode = self.client.session["batal_pekerjaan_captcha"]
        response = self.client.post(self.batal, {"captcha": kode}, follow=True)
        self.assertContains(response, "Tidak Aktif")
        self.assertFalse(DraftPemeriksaan.objects.filter(pemeriksa=user).exists())

    def test_opening_the_add_vehicle_form_is_active_until_saved_or_cancelled(self):
        user = self._login("Tim Penambahan Data")
        self.client.get(reverse("fleet:vehicle_create") + "?group=diesel&penambah=1", HTTP_HX_REQUEST="true")
        kerja = PekerjaanAktif.objects.get(user=user)
        self.assertEqual((kerja.jenis, kerja.keterangan), ("penambahan", "Kendaraan Diesel"))
        response = self.client.get(self.url)
        self.assertContains(response, "Penambahan Data")
        self.assertContains(response, "Kendaraan Diesel")
        self.client.get(self.batal)
        self.client.post(self.batal, {"captcha": self.client.session["batal_pekerjaan_captcha"]})
        self.assertFalse(PekerjaanAktif.objects.exists())

    def test_cancel_only_drops_own_work(self):
        lain = User.objects.create_user(username="lain", password="x")
        PekerjaanAktif.objects.create(user=lain, jenis="perbaikan", vehicle=self.vehicle)
        user = self._login("Tim Perbaikan")
        PekerjaanAktif.objects.create(user=user, jenis="perbaikan", vehicle=self.vehicle)
        self.assertContains(self.client.get(self.url), "Perbaikan")
        self.client.get(self.batal)
        self.client.post(self.batal, {"captcha": self.client.session["batal_pekerjaan_captcha"]})
        self.assertEqual(list(PekerjaanAktif.objects.values_list("user__username", flat=True)), ["lain"])

    def test_active_work_reopens_on_its_form(self):
        from accounts.models import Laporan, Satuan
        # Tim Pemeriksaan: the drafted inspection's vehicle is looked up again.
        user = self._login("Tim Pemeriksaan", "p1")
        halaman = reverse("accounts:pemeriksaan")
        self.assertNotContains(self.client.get(halaman), 'x-init="lookupNopol(')
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=user, data={"a": 1})
        self.assertContains(self.client.get(halaman), "x-init=\"lookupNopol('B 7 ST')\"")

        # Tim Perbaikan: the vehicle being repaired is loaded again.
        user = self._login("Tim Perbaikan", "p2")
        halaman = reverse("accounts:perbaikan")
        self.assertNotContains(self.client.get(halaman), 'x-init="muat(')
        PekerjaanAktif.objects.create(user=user, jenis="perbaikan", vehicle=self.vehicle)
        self.assertContains(self.client.get(halaman), "x-init=\"muat('B 7 ST')\"")

        # Tim Penambahan Data: the vehicle form opens again on its golongan.
        user = self._login("Tim Penambahan Data", "p3")
        Laporan.objects.create(
            akun=user, nip="1", nama="N", pangkat="P", jabatan="J",
            satuan=Satuan.objects.create(nama="S"), foto="laporan/x.jpg",
        )
        halaman = reverse("accounts:form_tambah")
        self.assertNotContains(self.client.get(halaman), "new CustomEvent('buka-tambah-kendaraan', { detail: { group: 'diesel'")
        PekerjaanAktif.objects.create(user=user, jenis="penambahan", keterangan="Kendaraan Diesel")
        self.assertContains(self.client.get(halaman), "{ detail: { group: 'diesel', matra: '")

    def test_dashboard_card_lists_repairs_and_additions_too(self):
        teknisi = User.objects.create_user(username="teknisi", password="x")
        penambah = User.objects.create_user(username="penambah", password="x")
        PekerjaanAktif.objects.create(user=teknisi, jenis="perbaikan", vehicle=self.vehicle)
        PekerjaanAktif.objects.create(user=penambah, jenis="penambahan", keterangan="Kendaraan Diesel")
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=teknisi, data={})
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard_partial"))  # the Kegiatan tab's part
        self.assertContains(response, "Perbaikan B 7 ST")
        self.assertContains(response, "Pemeriksaan B 7 ST")
        self.assertContains(response, "Penambahan kendaraan baru")
        self.assertContains(response, "Kendaraan Diesel · penambah")
        self.assertNotContains(response, "Tidak ada pekerjaan yang sedang berjalan.")

    def test_dashboard_cards_count_work_under_way(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")

        def angka():
            # The cards showing these are gone from the page; the counts are still made.
            hitung = self.client.get(reverse("accounts:dashboard_partial")).context["berlangsung_kendaraan"]
            return {nama.capitalize(): str(n) for nama, n in hitung.items()}

        # A saved vehicle (setUp) is not work under way.
        self.assertEqual(angka(), {"Penambahan": "0", "Pemeriksaan": "0", "Perbaikan": "0"})
        a, b = User.objects.create_user(username="a"), User.objects.create_user(username="b")
        PekerjaanAktif.objects.create(user=a, jenis="penambahan", keterangan="Kendaraan Diesel")
        PekerjaanAktif.objects.create(user=b, jenis="penambahan", keterangan='Golongan "B"')
        PekerjaanAktif.objects.create(user=a, jenis="perbaikan", vehicle=self.vehicle)
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=a, data={})
        self.assertEqual(angka(), {"Penambahan": "2", "Pemeriksaan": "1", "Perbaikan": "1"})
        PekerjaanAktif.objects.all().delete()
        self.assertEqual(angka()["Perbaikan"], "0")

    def test_admin_sees_the_status_of_their_own_tim_members(self):
        cabang = User.objects.create_user(username="cabang", password="rahasia-123")
        cabang.groups.add(Group.objects.get(name="Admin"))
        Anggota.objects.filter(pk=self.ketua.pk).update(admin=cabang)
        aktif = self._login("Tim Perbaikan", "sibuk")
        self._login("Tim Pemeriksaan", "santai")
        PekerjaanAktif.objects.create(user=aktif, jenis="perbaikan", vehicle=self.vehicle)
        # Another branch's member stays out.
        lain = User.objects.create_user(username="ketualain", password="x")
        lain.groups.add(Group.objects.get(name="Ketua Tim"))
        orang = User.objects.create_user(username="oranglain", password="x")
        orang.groups.add(Group.objects.get(name="Tim Perbaikan"))
        Anggota.add_root(user=lain).add_child(user=orang)

        for username in ("cabang",):
            self.client.login(username=username, password="rahasia-123")
            response = self.client.get(self.url)
            self.assertContains(response, f'<a href="{self.url}" class=')
            self.assertContains(response, "1 aktif")
            self.assertContains(response, "sibuk")
            self.assertContains(response, "Perbaikan B 7 ST")
            self.assertContains(response, "santai")
            self.assertContains(response, "Tidak Aktif")
            self.assertNotContains(response, "oranglain")
            self.assertNotContains(response, "Batalkan Pekerjaan")

    def test_superuser_opening_the_forms_leaves_nothing_behind(self):
        import json
        root = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        # A draft from before this rule isn't reopened, and goes away.
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=root, data={"a": 1})
        self.assertNotContains(self.client.get(reverse("accounts:pemeriksaan")), 'x-init="lookupNopol(')
        draft = reverse("accounts:pemeriksaan_draft", args=[self.vehicle.uuid])
        self.assertEqual(self.client.get(draft).json(), {})
        # The form's auto-save is accepted but nothing is stored.
        response = self.client.post(draft, json.dumps({"alat_1_kondisi": "B"}), content_type="application/json")
        self.assertEqual(response.json(), {"ok": True})
        self.assertFalse(DraftPemeriksaan.objects.exists())
        # Opening the repair list or the add-vehicle form isn't work under way.
        self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": self.vehicle.nopol})
        self.client.get(reverse("fleet:vehicle_create") + "?group=diesel&penambah=1", HTTP_HX_REQUEST="true")
        self.assertFalse(PekerjaanAktif.objects.exists())
        for nama in ("accounts:perbaikan", "accounts:form_tambah"):
            response = self.client.get(reverse(nama))
            self.assertNotContains(response, 'x-init="muat(')
            self.assertNotContains(response, "new CustomEvent('buka-tambah-kendaraan', { detail: { group: 'diesel'")

    def test_tim_member_draft_is_still_saved(self):
        import json
        user = self._login("Tim Pemeriksaan")
        draft = reverse("accounts:pemeriksaan_draft", args=[self.vehicle.uuid])
        self.client.post(draft, json.dumps({"alat_1_kondisi": "B"}), content_type="application/json")
        self.assertEqual(DraftPemeriksaan.objects.get(pemeriksa=user).data, {"alat_1_kondisi": "B"})
        self.assertEqual(self.client.get(draft).json(), {"alat_1_kondisi": "B"})
