"""Dashboard scope: a Ketua Tim sees the work of their own team only;
Admin, Pimpinan and superusers see everything."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts import dashboard
from accounts.models import Anggota, DraftPemeriksaan, PekerjaanAktif
from fleet.models import Vehicle


def _user(username, group):
    user = User.objects.create_user(username=username, password="rahasia-123")
    user.groups.add(Group.objects.get(name=group))
    return user


class _Cabang:
    """One branch: Admin > Ketua Tim > Tim member, with a
    vehicle the member added and work the member has under way."""

    def __init__(self, n):
        self.cabang = _user(f"cabang{n}", "Admin")
        self.ketua = _user(f"ketua{n}", "Ketua Tim")
        node = Anggota.add_root(user=self.ketua, admin=self.cabang)
        self.tim = _user(f"tim{n}", "Tim Pemeriksaan")
        node.add_child(user=self.tim)
        self.vehicle = Vehicle.objects.create(
            nopol=f"B {n} CK", merek="Uji", group_kendaraan="bermotor", ditambahkan_oleh=self.tim,
        )
        DraftPemeriksaan.objects.create(vehicle=self.vehicle, pemeriksa=self.tim, data={})
        PekerjaanAktif.objects.create(user=self.tim, jenis="perbaikan", vehicle=self.vehicle)

    @property
    def semua(self):
        return {self.cabang.pk, self.ketua.pk, self.tim.pk}


class DashboardCakupanTests(TestCase):
    def setUp(self):
        self.a, self.b = _Cabang(1), _Cabang(2)

    def test_cakupan_is_the_users_own_branch(self):
        self.assertEqual(dashboard.cakupan(self.a.cabang), self.a.semua)
        self.assertEqual(dashboard.cakupan(self.a.ketua), {self.a.ketua.pk, self.a.tim.pk})
        self.assertIsNone(dashboard.cakupan(_user("bos", "Pimpinan")))
        self.assertIsNone(dashboard.cakupan(User.objects.create_superuser(username="root", password="x")))

    def _lihat(self, username):
        self.client.login(username=username, password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_ketua_sees_only_their_team(self):
        for username in ("ketua1",):
            response = self._lihat(username)
            self.assertEqual(response.context["fleet_summary_kendaraan"]["total"], 1, username)
            self.assertEqual(
                response.context["berlangsung_kendaraan"], {"penambahan": 0, "pemeriksaan": 1, "perbaikan": 1}, username,
            )
            # The activity (the Kegiatan tab's part) keeps the same scope.
            partial = self.client.get(reverse("accounts:dashboard_partial"))
            self.assertContains(partial, "B 1 CK")
            self.assertNotContains(partial, "B 2 CK")

    def test_admin_pimpinan_and_superuser_see_everything(self):
        _user("bos", "Pimpinan")
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.assertIsNone(dashboard.cakupan_laporan(self.a.cabang))
        self.assertEqual(dashboard.cakupan_laporan(self.a.ketua), {self.a.ketua.pk, self.a.tim.pk})
        for username in ("cabang1", "bos", "root"):
            response = self._lihat(username)
            self.assertEqual(response.context["fleet_summary_kendaraan"]["total"], 2)
            kegiatan = self.client.get(reverse("accounts:dashboard_partial"))
            self.assertContains(kegiatan, "B 1 CK")
            self.assertContains(kegiatan, "B 2 CK")

    def test_ketua_tim_has_the_dashboard_menu(self):
        response = self._lihat("ketua1")
        self.assertContains(response, f'<a href="{reverse("accounts:dashboard")}" class=')

    def test_summary_cards_open_a_table_of_their_vehicles(self):
        Vehicle.objects.create(
            nopol="B 1 RB", merek="Rusak", group_kendaraan="diesel", status="dalam_perbaikan",
            ditambahkan_oleh=self.a.tim,
        )
        url = reverse("accounts:dashboard_kendaraan")
        response = self._lihat("ketua1")
        # The summary cards are gone from the page; their tables still answer.
        self.assertNotContains(response, f'hx-get="{url}?kartu=')
        self.assertNotContains(response, "Semua Matra")

        def isi(kartu):
            return self.client.get(url, {"kartu": kartu}).content.decode()

        # Own branch only, each card its own status.
        self.assertTrue("B 1 CK" in isi("total") and "B 1 RB" in isi("total") and "B 2 CK" not in isi("total"))
        self.assertTrue("B 1 CK" in isi("siap") and "B 1 RB" not in isi("siap"))
        self.assertTrue("B 1 RB" in isi("rusak_berat") and "B 1 CK" not in isi("rusak_berat"))
        self.assertIn("Tidak ada data.", isi("rusak_ringan"))
        self.assertEqual(self.client.get(url, {"kartu": "zzz"}).status_code, 404)
        _user("bos", "Pimpinan")
        self.client.login(username="bos", password="rahasia-123")
        self.assertIn("B 2 CK", isi("total"))

    def test_card_table_pages_past_15_rows_and_searches(self):
        for i in range(20):
            Vehicle.objects.create(
                nopol=f"Z {i:02d} PG", merek="Hino" if i == 7 else "Uji", group_kendaraan="diesel",
                ditambahkan_oleh=self.a.tim,
            )
        self.client.login(username="ketua1", password="rahasia-123")
        url = reverse("accounts:dashboard_kendaraan")
        # 21 vehicles: 15 on page 1, paged inside the modal.
        satu = self.client.get(url, {"kartu": "siap"}).content.decode()
        self.assertEqual(satu.count("<tr>"), 16)  # header + 15 rows
        self.assertIn("Menampilkan 1–15 dari 21 data", satu)
        self.assertIn('hx-target="#dashboard-modal-body"', satu)
        self.assertIn("kartu=siap&amp;page=2", satu)
        dua = self.client.get(url, {"kartu": "siap", "page": 2}).content.decode()
        self.assertEqual(dua.count("<tr>"), 7)
        self.assertIn(">16</td>", dua)
        # Search by merk; few rows, so no paging bar.
        cari = self.client.get(url, {"kartu": "siap", "q": "hino"}).content.decode()
        self.assertIn("Z 07 PG", cari)
        self.assertEqual(cari.count("<tr>"), 2)
        self.assertNotIn("Menampilkan", cari)
        self.assertIn('name="q" value="hino"', cari)
        self.assertIn("Tidak ada kendaraan yang cocok", self.client.get(url, {"kartu": "siap", "q": "zzzz"}).content.decode())
        # Search never leaves the viewer's branch.
        self.assertNotIn("B 2 CK", self.client.get(url, {"kartu": "total", "q": "CK"}).content.decode())

    def test_kegiatan_terbaru_pages_ten_at_a_time(self):
        for i in range(23):
            Vehicle.objects.create(nopol=f"K {i:02d} KG", merek="Uji", group_kendaraan="diesel", ditambahkan_oleh=self.a.tim)
        self.client.login(username="ketua1", password="rahasia-123")
        partial = reverse("accounts:dashboard_partial")
        satu = self.client.get(partial)
        self.assertEqual(len(satu.context["kegiatan_terbaru"]), 10)
        self.assertContains(satu, "Menampilkan 1–10 dari 24 kegiatan")
        self.assertContains(satu, f'hx-get="{partial}?matra=darat&amp;hal_kegiatan=2"')
        # The 10 s refresh asks for the page being shown.
        self.assertContains(satu, f'hx-get="{partial}?matra=darat&amp;hal_kegiatan=1"')
        tiga = self.client.get(partial, {"hal_kegiatan": 3})
        self.assertEqual(len(tiga.context["kegiatan_terbaru"]), 4)
        self.assertContains(tiga, f'hx-get="{partial}?matra=darat&amp;hal_kegiatan=3"')
        self.assertContains(tiga, "Menampilkan 21–24 dari 24 kegiatan")


class DashboardMatraTests(TestCase):
    """The matra picked above the dashboard's tabs narrows it to that matra's users."""

    def setUp(self):
        from accounts.models import AkunPublik
        self.tim = {}
        for n, matra in (("d", "darat"), ("l", "laut")):
            admin = _user(f"admin_{n}", "Admin")
            AkunPublik.objects.filter(user=admin).update(matra=matra)
            ketua = _user(f"ketua_{n}", "Ketua Tim")
            node = Anggota.add_root(user=ketua, admin=admin)
            # Made before a matra was asked of them: they follow their Admin's.
            self.tim[n] = _user(f"tim_{n}", "Tim Penambahan Data")
            node.add_child(user=self.tim[n])
            Vehicle.objects.create(nopol=f"M {n.upper()} 1", merek="Uji", group_kendaraan="rantis", ditambahkan_oleh=self.tim[n])
        # One member with a matra of their own, different from their Admin's.
        sendiri = _user("tim_udara", "Tim Penambahan Data")
        AkunPublik.objects.filter(user=sendiri).update(matra="udara")
        Anggota.objects.get(user__username="ketua_d").add_child(user=sendiri)
        Vehicle.objects.create(nopol="M U 1", merek="Uji", group_kendaraan="rantis", ditambahkan_oleh=sendiri)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")

    def _total(self, **query):
        response = self.client.get(reverse("accounts:dashboard"), query)
        return response, response.context["fleet_summary_kendaraan"]["total"]

    def test_matra_narrows_the_dashboard(self):
        # No all-matra view: without a matra picked it is the first one.
        response, bawaan = self._total()
        self.assertEqual((bawaan, response.context["matra_dashboard"]), (1, "darat"))
        self.assertNotContains(response, "Semua Matra")
        for label in ("Matra Darat", "Matra Laut", "Matra Udara"):
            self.assertContains(response, label)
        self.assertEqual(dashboard.pengguna_matra("darat") & {t.pk for t in self.tim.values()}, {self.tim["d"].pk})
        for matra, nopol in (("darat", "M D 1"), ("laut", "M L 1"), ("udara", "M U 1")):
            response, total = self._total(matra=matra)
            self.assertEqual(total, 1, matra)
            self.assertEqual(response.context["matra_dashboard"], matra)
            self.assertEqual(sum(b["total"] for _, baris, _ in response.context["status_satuan"] for b in baris), 1, matra)
            # The 10 s refresh keeps the matra.
            self.assertContains(response, f"dashboard/partial/?matra={matra}&amp;hal_kegiatan=")
            partial = self.client.get(reverse("accounts:dashboard_partial"), {"matra": matra})
            self.assertContains(partial, nopol)
            for lain in {"M D 1", "M L 1", "M U 1"} - {nopol}:
                self.assertNotContains(partial, lain)
        self.assertEqual(self._total(matra="zzz")[1], 1)
        # A vehicle counts for the matra it was added for (Form Tambah), whoever added it,
        # and one with no matra anywhere counts for the first.
        Vehicle.objects.create(nopol="M X 1", merek="Uji", group_kendaraan="rantis", ditambahkan_oleh=self.tim["d"], matra="laut")
        Vehicle.objects.create(nopol="M X 2", merek="Uji", group_kendaraan="rantis")
        root = User.objects.get(username="root")
        Vehicle.objects.create(nopol="M X 3", merek="Uji", group_kendaraan="rantis", ditambahkan_oleh=root)
        self.assertEqual([self._total(matra=m)[1] for m in ("darat", "laut", "udara")], [3, 2, 1])

    def test_admin_and_pimpinan_tim_see_their_own_matra_only(self):
        from accounts.models import AkunPublik
        self.client.login(username="admin_d", password="rahasia-123")
        # Their teams hold a darat and an udara vehicle; only their matra's shows, whatever is asked.
        for query in ({}, {"matra": "laut"}, {"matra": "udara"}):
            response, total = self._total(**query)
            self.assertEqual((total, response.context["matra_dashboard"]), (1, "darat"), query)
            self.assertNotContains(response, "Semua Matra")
            self.assertNotContains(response, 'aria-label="Matra"')
        pimpinan_tim = _user("pimtim", "Pimpinan Ketua Tim")
        AkunPublik.objects.filter(user=pimpinan_tim).update(matra="laut")
        self.client.login(username="pimtim", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"), {"matra": "darat"})
        self.assertEqual(response.context["matra_dashboard"], "laut")
        self.assertNotContains(response, "Semua Matra")
        # A Ketua Tim too: their own matra, or their Admin's when they have none.
        self.client.login(username="ketua_l", password="rahasia-123")
        for query in ({}, {"matra": "darat"}):
            response = self.client.get(reverse("accounts:dashboard"), query)
            self.assertEqual(response.context["matra_dashboard"], "laut", query)
            self.assertNotContains(response, 'aria-label="Matra"')
        self.assertEqual(response.context["fleet_summary_kendaraan"]["total"], 1)  # the laut team's vehicle only
        # A Pimpinan, like the superuser, picks any matra.
        _user("pimpinan1", "Pimpinan")
        self.client.login(username="pimpinan1", password="rahasia-123")
        response, total = self._total(matra="udara")
        self.assertEqual((total, response.context["matra_dashboard"]), (1, "udara"))
        self.assertContains(response, 'aria-label="Matra"')
        self.assertNotContains(response, "Semua Matra")


class DashboardSparepartRusakTests(TestCase):
    """The parts that are Rusak Berat now (Laporan Rusak's Sparepart tab)."""

    def test_lists_parts_still_rusak_berat(self):
        from accounts.models import Laporan, PemeriksaanRantis, PemeriksaanRantisItem, PerbaikanRantis, Satuan
        bio = Laporan.objects.create(nip="1", nama="BUDI", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="YON UJI"))
        v = Vehicle.objects.create(nopol="R 1 SP", merek="Maung", group_kendaraan="rantis")
        lama = PemeriksaanRantis.objects.create(
            pemeriksa=bio, vehicle=v, km_berfungsi="ya", jam_mesin_berfungsi="ya", buku_pemeliharaan="ada",
            kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        PemeriksaanRantisItem.objects.create(pemeriksaan=lama, nomor=9, nama_alat="Lama", kondisi="RB")  # an older inspection
        hasil = PemeriksaanRantis.objects.create(
            pemeriksa=bio, vehicle=v, km_berfungsi="ya", jam_mesin_berfungsi="ya", buku_pemeliharaan="ada",
            kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        item = {
            nama: PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=n, nama_alat=nama, kondisi=kondisi, keterangan=f"ket {nama}")
            for n, (nama, kondisi) in enumerate(
                (("Rusak", "RB"), ("Diperbaiki", "RB"), ("MasihRusak", "RR"), ("Ringan", "RR"), ("Baik", "B")), start=1,
            )
        }
        PerbaikanRantis.objects.create(teknisi=bio, item=item["Diperbaiki"], kondisi="B")
        PerbaikanRantis.objects.create(teknisi=bio, item=item["MasihRusak"], kondisi="RB", keterangan="tidak ada suku cadang")
        daftar, total = dashboard.sparepart_rusak(None)
        self.assertEqual(total, 2)
        self.assertEqual({b["item"].nama_alat: b["keterangan"] for b in daftar}, {"Rusak": "ket Rusak", "MasihRusak": "tidak ada suku cadang"})
        # The dashboard no longer has a Rusak/Tidak Bisa Diperbaiki tab.
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, "RUSAK/TIDAK BISA DIPERBAIKI")
        self.assertNotIn("sparepart_rusak", response.context)
