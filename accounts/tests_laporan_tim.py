"""Laporan Tim: team activity counted through the account that saved it."""
import tempfile

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import (
    Anggota,
    Laporan,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanGolonganB,
    Satuan,
)
from fleet.models import Vehicle


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanTimTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        self.vehicle = Vehicle.objects.create(nopol="B 1 X", merek="Hino")
        self.ketua, self.node = self._ketua("alpha")
        self.periksa = self._anggota(self.node, "periksa1", "Tim Pemeriksaan")
        self.perbaiki = self._anggota(self.node, "perbaiki1", "Tim Perbaikan")

    def _ketua(self, username):
        user = User.objects.create_user(username=username, password="x")
        user.groups.add(Group.objects.get(name="Ketua Tim"))
        return user, Anggota.add_root(user=user)

    def _anggota(self, node, username, grup):
        user = User.objects.create_user(username=username, password="x")
        user.groups.add(Group.objects.get(name=grup))
        Anggota.objects.get(pk=node.pk).add_child(user=user)
        return user

    def _biodata(self, akun):
        return Laporan.objects.create(
            nip="1", nama="Budi", pangkat="Kapten", jabatan="Teknisi", satuan=self.satuan, foto="x.gif", akun=akun,
        )

    def _pemeriksaan(self, akun):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=self._biodata(akun), vehicle=self.vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada",
        )
        return PemeriksaanGolonganBItem.objects.create(pemeriksaan=hasil, nomor=1, nama_alat="Motor", kondisi="RB")

    def test_menu_and_team_counts(self):
        item = self._pemeriksaan(self.periksa)
        self._pemeriksaan(self.periksa)
        PerbaikanGolonganB.objects.create(teknisi=self._biodata(self.perbaiki), item=item, kondisi="B")
        Vehicle.objects.create(nopol="B 2 X", merek="Isuzu", ditambahkan_oleh=self.ketua)
        # Someone outside the team doesn't count.
        self._pemeriksaan(User.objects.get(username="root"))
        self._ketua("bravo")

        response = self.client.get(reverse("accounts:laporan_tim"))
        self.assertContains(response, f'href="{reverse("accounts:laporan_tim")}"')
        rows = [baris for baris, _ in response.context["halaman"]]
        self.assertEqual(rows, [("alpha", 2, 2, 1, 1, 4), ("bravo", 0, 0, 0, 0, 0)])
        self.assertContains(response, f'hx-get="{reverse("accounts:laporan_tim_detail", args=[self.node.uuid])}"')

    def test_filters_reach_counts_and_modal(self):
        self._pemeriksaan(self.periksa)
        diesel = self.client.get(reverse("accounts:laporan_tim"), {"golongan": "diesel"})
        self.assertEqual(diesel.context["halaman"][0][0][2], 0)
        detail = reverse("accounts:laporan_tim_detail", args=[self.node.uuid])
        self.assertContains(diesel, f'hx-get="{detail}?golongan=diesel"')

    def test_modal_members_activity_and_pdf(self):
        item = self._pemeriksaan(self.periksa)
        PerbaikanGolonganB.objects.create(teknisi=self._biodata(self.perbaiki), item=item, kondisi="B")
        response = self.client.get(reverse("accounts:laporan_tim_detail", args=[self.node.uuid]))
        self.assertContains(response, "Anggota Tim")
        self.assertContains(response, "Aktivitas Tim")
        # The three activity cards open a popup listing the team's activities of that kind.
        for jenis in ("Pemeriksaan", "Perbaikan", "Penambahan"):
            self.assertContains(response, f"""@click="kartu = '{jenis}'\"""")
        # Both popups show 15 rows a page.
        self.assertContains(response, "PER_HAL: 15")
        self.assertContains(response, 'x-for="(a, i) in halamanIni(daftarKartu)"')
        self.assertContains(response, 'x-for="(a, i) in halamanIni(filteredTab)"')
        # The Ketua Tim (alpha) heads the modal; the table lists the members only.
        self.assertEqual([u.username for u in response.context["anggota"]], ["perbaiki1", "periksa1"])
        self.assertEqual(response.context["anggota"][1].jumlah["pemeriksaan"], 1)
        self.assertEqual([a["kegiatan"] for a in response.context["aktivitas"]], ["Perbaikan", "Pemeriksaan"])
        pdf = self.client.get(reverse("accounts:laporan_tim_pdf", args=[self.node.uuid]))
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_query_counts_do_not_grow(self):
        def hitung(url):
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url)
            return len(ctx)
        daftar = reverse("accounts:laporan_tim")
        detail = reverse("accounts:laporan_tim_detail", args=[self.node.uuid])
        self._pemeriksaan(self.periksa)
        sedikit = (hitung(daftar), hitung(detail))
        for i in range(3):
            _, node = self._ketua(f"ketua{i}")
            anggota = self._anggota(node, f"anggota{i}", "Tim Pemeriksaan")
            self._pemeriksaan(anggota)
            item = self._pemeriksaan(self.periksa)
            PerbaikanGolonganB.objects.create(teknisi=self._biodata(self.perbaiki), item=item, kondisi="B")
        self.assertEqual(sedikit, (hitung(daftar), hitung(detail)))

    def test_tim_roles_cannot_open_it(self):
        self.client.login(username="periksa1", password="x")
        self.assertNotEqual(self.client.get(reverse("accounts:laporan_tim")).status_code, 200)
