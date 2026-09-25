"""N+1 guards: a page's query count must not grow with the amount of data.

Each check renders a page with a small and a larger data set and compares
the number of queries.
"""
import tempfile

from django.contrib import admin
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
from fleet.models import Vehicle, VehiclePhoto


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class QueryCountTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        self.teknisi = Laporan.objects.create(
            nip="1", nama="Budi", pangkat="Kapten", jabatan="Teknisi", satuan=self.satuan, foto="x.gif",
        )

    def _kendaraan(self, n, start=0):
        vehicles = []
        for i in range(start, start + n):
            v = Vehicle.objects.create(nopol=f"B {i} X", merek="Hino", no_chasis=f"C{i}", no_mesin=f"M{i}")
            for j in range(4):
                VehiclePhoto.objects.create(vehicle=v, image=f"kendaraan/{i}-{j}.jpg")
            vehicles.append(v)
        return vehicles

    def _pemeriksaan(self, vehicle, rusak):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=self.teknisi, vehicle=vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", kesatuan=self.satuan,
        )
        for nomor in range(1, 41):
            item = PemeriksaanGolonganBItem.objects.create(
                pemeriksaan=hasil, nomor=nomor, nama_alat=f"Alat {nomor}",
                kondisi="RB" if nomor <= rusak else "B",
            )
            if nomor <= rusak:
                PerbaikanGolonganB.objects.create(teknisi=self.teknisi, item=item, kondisi="RR", keterangan="x")
        return hasil

    def _hitung(self, url, params=None):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params or {})
        self.assertIn(response.status_code, (200, 302), url)
        return len(ctx)

    def _tanpa_n_plus_1(self, url, tambah, params=None):
        sedikit = self._hitung(url, params)
        tambah()
        banyak = self._hitung(url, params)
        self.assertEqual(sedikit, banyak, f"{url}: {sedikit} queries with little data, {banyak} with more")

    def test_jadwal_and_servis(self):
        from fleet.models import Jadwal, Servis

        def tambah():
            for v in self._kendaraan(3, start=200 + Vehicle.objects.count()):
                Jadwal.objects.create(vehicle=v, tanggal="2026-10-01", kegiatan="servis")
                Servis.objects.create(vehicle=v, tanggal="2026-09-01", jenis_servis="Oli", biaya=100000)
        tambah()
        self._tanpa_n_plus_1(reverse("operasional:jadwal_list"), tambah)
        self._tanpa_n_plus_1(reverse("operasional:servis_list"), tambah)

    def test_laporan_pages(self):
        (vehicle,) = self._kendaraan(1)
        self._pemeriksaan(vehicle, rusak=2)

        def tambah():
            for v in self._kendaraan(3, start=300 + Vehicle.objects.count()):
                self._pemeriksaan(v, rusak=2)
        for name in ("accounts:laporan_pemeriksaan", "accounts:laporan_perbaikan", "accounts:laporan_penambahan"):
            self._tanpa_n_plus_1(reverse(name), tambah)

    def test_armada_list_and_search(self):
        self._kendaraan(2)
        self._tanpa_n_plus_1(reverse("fleet:vehicle_list"), lambda: self._kendaraan(6, start=10))
        self._tanpa_n_plus_1(reverse("fleet:vehicle_search"), lambda: self._kendaraan(6, start=30))

    def test_history_and_perbaikan_for_one_vehicle(self):
        (vehicle,) = self._kendaraan(1)
        self._pemeriksaan(vehicle, rusak=2)
        for name in ("accounts:history_kendaraan", "accounts:perbaikan_kendaraan", "accounts:history_kendaraan_modal"):
            self._tanpa_n_plus_1(
                reverse(name), lambda: [self._pemeriksaan(vehicle, rusak=10) for _ in range(3)], {"nopol": vehicle.nopol},
            )

    def test_pengaturan_users_and_satuan(self):
        def tambah():
            ketua = User.objects.create_user(username=f"ketua{User.objects.count()}", password="x")
            ketua.groups.add(Group.objects.get(name="Ketua Tim"))
            node = Anggota.add_root(user=ketua)
            for i in range(3):
                anggota = User.objects.create_user(username=f"{ketua.username}-a{i}", password="x")
                anggota.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
                Anggota.objects.get(pk=node.pk).add_child(user=anggota)
            Satuan.objects.create(nama=f"Satuan {User.objects.count()}")
        tambah()
        self._tanpa_n_plus_1(reverse("accounts:pengaturan"), lambda: [tambah() for _ in range(3)])

    def test_admin_changelists(self):
        (vehicle,) = self._kendaraan(1)
        self._pemeriksaan(vehicle, rusak=1)

        def tambah():
            for v in self._kendaraan(3, start=100 + Vehicle.objects.count()):
                self._pemeriksaan(v, rusak=2)
        urls = [
            reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
            for model in admin.site._registry
            if model._meta.app_label in ("accounts", "fleet")
        ]
        sedikit = {url: self._hitung(url) for url in urls}
        tambah()
        banyak = {url: self._hitung(url) for url in urls}
        tumbuh = {url: (sedikit[url], banyak[url]) for url in urls if sedikit[url] != banyak[url]}
        self.assertEqual(tumbuh, {}, "admin changelists whose query count grows with data")
