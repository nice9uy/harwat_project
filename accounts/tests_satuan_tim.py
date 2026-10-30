"""A Tim member's Satuan follows their Ketua Tim's, and so does the work they
are credited with in the reports and the dashboard."""
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.forms import simpan_satuan, terapkan_keanggotaan
from accounts.models import AkunPublik, Anggota, Laporan, Satuan
from fleet.models import Vehicle


def _akun(username, grup):
    user = User.objects.create_user(username=username, password="rahasia-123")
    user.groups.add(Group.objects.get(name=grup))
    return user


class SatuanTimTests(TestCase):
    def setUp(self):
        self.a, self.b = Satuan.objects.create(nama="Satuan A"), Satuan.objects.create(nama="Satuan B")
        self.ketua = _akun("ketua_a", "Ketua Tim")
        self.node = Anggota.add_root(user=self.ketua)
        simpan_satuan(self.ketua, self.a)
        self.tim = _akun("tim_b", "Tim Penambahan Data")
        Anggota.objects.get(pk=self.node.pk).add_child(user=self.tim)

    def _biodata(self, user, satuan):
        return Laporan.objects.create(akun=user, nip=user.username, nama=user.username.upper(), pangkat="P", jabatan="J", satuan=satuan, foto="x.jpg")

    def test_a_member_s_biodata_and_account_take_the_ketua_s_unit(self):
        biodata = self._biodata(self.tim, self.b)
        biodata.refresh_from_db()
        self.assertEqual(biodata.satuan, self.a)
        simpan_satuan(self.tim, self.b)
        self.assertEqual(AkunPublik.objects.get(user=self.tim).satuan, self.a)

    def test_vehicles_a_member_adds_count_for_the_ketua_s_unit(self):
        Vehicle.objects.create(nopol="B 1 ZZ", merek="Uji", group_kendaraan="B", ditambahkan_oleh=self.tim, penambah=self._biodata(self.tim, self.b))
        self.assertEqual(list(Vehicle.objects.values_list("penambah__satuan__nama", flat=True)), ["Satuan A"])

    def test_the_team_follows_a_change_of_the_ketua_s_unit_and_a_move(self):
        self._biodata(self.tim, self.b)
        simpan_satuan(self.ketua, self.b)
        self.assertEqual(Laporan.objects.get(akun=self.tim).satuan, self.b)
        ketua_c = _akun("ketua_c", "Ketua Tim")
        node_c = Anggota.add_root(user=ketua_c)
        simpan_satuan(ketua_c, self.a)
        terapkan_keanggotaan(self.tim, "tim_penambahan_data", node_c)
        self.assertEqual(Laporan.objects.get(akun=self.tim).satuan, self.a)

    def test_info_profile_shows_the_unit_locked(self):
        self._biodata(self.tim, self.a)
        self.client.login(username="tim_b", password="rahasia-123")
        form = self.client.get(reverse("accounts:info_profile_edit"), HTTP_HX_REQUEST="true")
        self.assertContains(form, "Mengikuti satuan Ketua Tim Anda.")
        self.assertContains(form, "Satuan A")

    def test_command_for_older_data(self):
        lama = self._biodata(self.tim, self.a)
        Laporan.objects.filter(pk=lama.pk).update(satuan=self.b)  # as before the rule
        keluar = StringIO()
        call_command("samakan_satuan_tim", stdout=keluar)
        self.assertIn("tim_b: Satuan A, Satuan B -> Satuan A", keluar.getvalue())
        self.assertEqual(Laporan.objects.get(pk=lama.pk).satuan, self.b)  # only shown
        call_command("samakan_satuan_tim", "--terapkan", stdout=StringIO())
        self.assertEqual(Laporan.objects.get(pk=lama.pk).satuan, self.a)
