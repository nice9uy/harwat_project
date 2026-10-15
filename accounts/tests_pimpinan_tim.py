"""Pimpinan Tim: a Pimpinan over the Ketua Tim they pick, seeing those teams only."""
import re

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts import dashboard, roles
from accounts.models import Anggota, BawahanPimpinan
from fleet.models import Vehicle


def _user(username, group):
    user = User.objects.create_user(username=username, password="rahasia-123")
    user.groups.add(Group.objects.get(name=group))
    return user


class PimpinanTimTests(TestCase):
    def setUp(self):
        self.pt = _user("pt1", "Pimpinan Ketua Tim")
        self.ketua, self.tim = {}, {}
        for n in ("a", "b", "c"):
            self.ketua[n] = Anggota.add_root(user=_user(f"ketua_{n}", "Ketua Tim"))
            self.tim[n] = _user(f"tim_{n}", "Tim Penambahan Data")
            Anggota.objects.get(pk=self.ketua[n].pk).add_child(user=self.tim[n])
            Vehicle.objects.create(nopol=f"UJI {n.upper()}", merek="X", ditambahkan_oleh=self.tim[n])
        self.url = reverse("accounts:pimpinan_tim_bawahan", args=[self.pt.publik.uuid])
        self.client.login(username="pt1", password="rahasia-123")

    def _pilih(self, *nama):
        return self.client.post(self.url, {"ketua": [str(self.ketua[n].uuid) for n in nama]})

    def test_role_and_menus(self):
        self.assertEqual(dict(roles.KEANGGOTAAN)["pimpinan_tim"], "Pimpinan Ketua Tim")
        self.assertEqual(dict(roles.KEANGGOTAAN)["pimpinan"], "Pimpinan")
        self.assertEqual(roles.keanggotaan_kode(self.pt), "pimpinan_tim")
        menus = roles.allowed_menus(self.pt)
        self.assertIn("anggota_tim", menus)
        self.assertIn("laporan_tim", menus)
        for bukan in ("pengaturan", "form_group", "armada", "pemeriksaan"):
            self.assertNotIn(bukan, menus)
        self.assertEqual(self.client.get(reverse("accounts:pengaturan")).status_code, 302)

    def test_picks_own_ketua_tim_and_sees_only_those_teams(self):
        kosong = self.client.get(reverse("accounts:anggota_tim"))
        self.assertContains(kosong, "Pilih Ketua Tim")
        self.assertContains(kosong, "Belum ada Ketua Tim yang dipilih")
        modal = self.client.get(self.url)
        for n in "abc":
            self.assertContains(modal, f'value="{self.ketua[n].uuid}"')
        self.assertRedirects(self._pilih("a", "b"), reverse("accounts:anggota_tim"))
        self.assertEqual(BawahanPimpinan.objects.filter(pimpinan=self.pt).count(), 2)

        halaman = self.client.get(reverse("accounts:anggota_tim")).content.decode()
        for ada in ("ketua_a", "tim_a", "ketua_b", "tim_b"):
            self.assertIn(ada, halaman)
        self.assertNotIn("ketua_c", halaman)
        # Looks, doesn't manage: no + Anggota, and the add view refuses.
        self.assertNotIn("+ Anggota", halaman)
        tambah = reverse("accounts:anggota_tim_tambah", args=[self.ketua["a"].uuid])
        self.assertEqual(self.client.post(tambah, {"username": "x", "keanggotaan": "tim_perbaikan", "matra": "darat"}).status_code, 403)

        self.assertEqual(
            dashboard.cakupan(self.pt),
            {self.pt.pk, self.ketua["a"].user_id, self.tim["a"].pk, self.ketua["b"].user_id, self.tim["b"].pk},
        )
        dasbor = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(dasbor.context["fleet_summary_kendaraan"]["total"], 2)

        laporan = self.client.get(reverse("accounts:laporan_tim"))
        self.assertEqual([baris[0] for baris, _ in laporan.context["halaman"]], ["ketua_a", "ketua_b"])
        self.assertEqual(self.client.get(reverse("accounts:laporan_tim_detail", args=[self.ketua["a"].uuid])).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:laporan_tim_detail", args=[self.ketua["c"].uuid])).status_code, 404)

        # Picking again replaces the choice.
        self._pilih("c")
        self.assertEqual(
            list(BawahanPimpinan.objects.filter(pimpinan=self.pt).values_list("ketua__user__username", flat=True)),
            ["ketua_c"],
        )

    def test_who_may_pick(self):
        lain = _user("pt2", "Pimpinan Ketua Tim")
        url_lain = reverse("accounts:pimpinan_tim_bawahan", args=[lain.publik.uuid])
        self.assertEqual(self.client.get(url_lain).status_code, 403)  # not for another Pimpinan Tim
        _user("admin1", "Admin")
        self.client.login(username="admin1", password="rahasia-123")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertContains(self.client.get(reverse("accounts:pengaturan")), self.url)
        self.assertRedirects(self._pilih("b"), reverse("accounts:pengaturan"))
        self.assertEqual(BawahanPimpinan.objects.get(pimpinan=self.pt).ketua, self.ketua["b"])
        # Only a Pimpinan Tim has subordinates to pick.
        bos = _user("bos", "Pimpinan")
        self.assertEqual(self.client.get(reverse("accounts:pimpinan_tim_bawahan", args=[bos.publik.uuid])).status_code, 403)

    def test_pimpinan_still_sees_everything_and_a_role_change_drops_the_choice(self):
        bos = _user("bos", "Pimpinan")
        self.assertIsNone(dashboard.cakupan(bos))
        self._pilih("a")
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.client.post(reverse("accounts:user_edit", args=[self.pt.publik.uuid]), {"keanggotaan": "pimpinan", "matra": "darat"})
        self.assertEqual(roles.keanggotaan_kode(self.pt), "pimpinan")
        self.assertFalse(BawahanPimpinan.objects.exists())
        # A Pimpinan Tim is made with a matra and at least one Ketua Tim.
        buat = reverse("accounts:user_create")
        gagal = self.client.post(buat, {"username": "pt9", "keanggotaan": "pimpinan_tim"})
        self.assertContains(gagal, "Pilih matra untuk user ini.")
        self.assertContains(gagal, "Pilih minimal satu Ketua Tim untuk Pimpinan Ketua Tim ini.")
        self.assertFalse(User.objects.filter(username="pt9").exists())
        self.client.post(buat, {
            "username": "pt9", "keanggotaan": "pimpinan_tim", "matra": "laut",
            "bawahan": [self.ketua["a"].pk, self.ketua["c"].pk],
        })
        pt9 = User.objects.get(username="pt9")
        self.assertEqual(pt9.publik.matra, "laut")
        self.assertEqual(
            set(BawahanPimpinan.objects.filter(pimpinan=pt9).values_list("ketua__user__username", flat=True)),
            {"ketua_a", "ketua_c"},
        )
        # Edit shows them ticked and replaces the choice; a Pimpinan needs neither.
        edit = reverse("accounts:user_edit", args=[pt9.publik.uuid])
        form = self.client.get(edit).content.decode()
        self.assertEqual(len(re.findall(r'name="bawahan"[^>]*checked', form)), 2)
        self.client.post(edit, {"keanggotaan": "pimpinan_tim", "matra": "laut", "bawahan": [self.ketua["b"].pk]})
        self.assertEqual(BawahanPimpinan.objects.get(pimpinan=pt9).ketua, self.ketua["b"])
        self.client.post(buat, {"username": "bos2", "keanggotaan": "pimpinan"})
        self.assertEqual(roles.keanggotaan_kode(User.objects.get(username="bos2")), "pimpinan")
        # Tambah User offers both roles.
        form = self.client.get(reverse("accounts:user_create"), HTTP_HX_REQUEST="true")
        self.assertContains(form, 'value="pimpinan"')
        self.assertContains(form, 'value="pimpinan_tim"')


class PimpinanTanpaFormTests(TestCase):
    """A Pimpinan has no Kegiatan forms: not in the sidebar, not by URL."""

    def test_pimpinan_has_no_tim_forms(self):
        from django.urls import reverse
        from accounts import roles
        user = User.objects.create_user(username="pimpinan_x", password="rahasia-123")
        user.groups.add(Group.objects.get(name="Pimpinan"))
        menus = roles.allowed_menus(user)
        self.assertFalse(menus & {"pemeriksaan", "form_tambah", "perbaikan", "rusak", "status", "armada", "backup", "pengaturan", "jadwal", "servis"})
        self.assertTrue({"dashboard", "history", "laporan_rusak", "laporan_tim", "rekap_kerusakan"} <= menus)
        self.client.login(username="pimpinan_x", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:dashboard"))
        for nama in ("accounts:pemeriksaan", "accounts:form_tambah", "accounts:perbaikan", "accounts:rusak", "accounts:pengaturan"):
            self.assertNotContains(halaman, f'href="{reverse(nama)}"')
            self.assertEqual(self.client.get(reverse(nama)).status_code, 302, nama)
        self.assertEqual(self.client.get(reverse("fleet:vehicle_create") + "?group=B").status_code, 302)


class PimpinanHanyaOlehSuperuserTests(TestCase):
    """Only a superuser makes, changes or deletes a Pimpinan."""

    def test_admin_cannot_make_or_touch_a_pimpinan(self):
        from accounts.forms import UserCreateForm
        self.assertFalse(roles.boleh_kelola(roles.ADMIN_ROLE, "pimpinan"))
        self.assertTrue(roles.boleh_kelola(roles.SUPERUSER, "pimpinan"))
        self.assertTrue(roles.boleh_kelola(roles.ADMIN_ROLE, roles.KETUA_TIM))
        admin = _user("admin_p", "Admin")
        pimpinan = _user("pimpinan_p", "Pimpinan")
        self.client.login(username="admin_p", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:user_create"))
        self.assertNotContains(halaman, 'value="pimpinan"')
        self.client.post(reverse("accounts:user_create"), {
            "username": "pimpinan_baru", "keanggotaan": "pimpinan", "password1": "Rahasia-12345", "password2": "Rahasia-12345",
        })
        self.assertFalse(User.objects.filter(username="pimpinan_baru").exists())
        self.client.post(reverse("accounts:user_delete", args=[pimpinan.publik.uuid]))
        self.assertTrue(User.objects.filter(pk=pimpinan.pk).exists())
        self.client.post(reverse("accounts:user_reset_password", args=[pimpinan.publik.uuid]))
        self.assertTrue(User.objects.get(pk=pimpinan.pk).check_password("rahasia-123"))


class SatuanAkunTests(TestCase):
    """Tambah User / Edit ask the account's unit (typed, with suggestions); the user table shows it."""

    def test_pick_unit_on_create_and_edit_and_see_it_in_the_table(self):
        from accounts.models import AkunPublik, Laporan, Satuan
        yon = Satuan.objects.create(nama="YONIF 202")
        kodam = Satuan.objects.create(nama="KODAM JAYAKARTA")
        User.objects.create_superuser(username="root_sat", password="rahasia-123")
        self.client.login(username="root_sat", password="rahasia-123")
        form = self.client.get(reverse("accounts:user_create"), HTTP_HX_REQUEST="true")
        self.assertContains(form, "x-data=\"autocomplete('opsi-satuan-akun'")
        self.assertContains(form, "YONIF 202")
        self.client.post(reverse("accounts:user_create"), {
            "username": "kasat", "keanggotaan": "pimpinan", "satuan": yon.pk,
        }, HTTP_HX_REQUEST="true")
        akun = User.objects.get(username="kasat")
        self.assertEqual(akun.publik.satuan, yon)
        # Edit: shown filled in, and changed.
        edit = reverse("accounts:user_edit", args=[akun.publik.uuid])
        self.assertContains(self.client.get(edit, HTTP_HX_REQUEST="true"), f'name="satuan" :value="nilai" value="{yon.pk}"')
        self.client.post(edit, {"keanggotaan": "pimpinan", "satuan": kodam.pk}, HTTP_HX_REQUEST="true")
        self.assertEqual(AkunPublik.objects.get(user=akun).satuan, kodam)
        # The table's Satuan column, after Matra; without one picked, the unit of their biodata.
        lama = _user("lama", "Pimpinan")
        Laporan.objects.create(akun=lama, nip="1", nama="L", pangkat="P", jabatan="J", satuan=yon)
        tabel = self.client.get(reverse("accounts:pengaturan"))
        isi = tabel.content.decode()
        self.assertLess(isi.index(">Matra</th>"), isi.index(">Satuan</th>"))
        baris = {u.username: u.satuan_label for u in tabel.context["users"]}
        self.assertEqual((baris["kasat"], baris["lama"]), ("KODAM JAYAKARTA", "YONIF 202"))
