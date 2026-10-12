"""How the heavy pages grow with the data: fills a throwaway test database
with N vehicles (each inspected, half of them repaired) for growing N and
times the pages. Doubling N should about double the time (linear); a time
that quadruples is quadratic.

    .venv/bin/python manage.py shell < scripts/uji_skala.py
    UKURAN=500,1000,2000,4000,8000 .venv/bin/python manage.py shell < scripts/uji_skala.py

Nothing touches the real database: Django's test database is made, used and
dropped (in memory for SQLite).
"""
import logging
import os
import time

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext, setup_test_environment, teardown_test_environment
from django.test.runner import DiscoverRunner

from accounts.models import (
    AkunPublik, Anggota, KmJadwal, Laporan, PemeriksaanGolonganB, PemeriksaanGolonganBItem, PerbaikanGolonganB,
    Satuan,
)
from fleet.models import Servis, Vehicle

UKURAN = [int(n) for n in os.environ.get("UKURAN", "500,1000,2000,4000").split(",")]
HALAMAN = [
    ("Dashboard Semua Matra", "/dashboard/"),
    ("Dashboard Matra Darat", "/dashboard/?matra=darat"),
    ("Dashboard refresh 10 dtk", "/dashboard/partial/?matra=darat"),
    ("Servis", "/servis/"),
    ("Servis halaman terakhir", "/servis/?page=999999"),
    ("Laporan Rusak Sparepart", "/laporan-rusak/?tab=sparepart"),
    ("Laporan Pemeriksaan", "/laporan-pemeriksaan/"),
    ("Laporan Tim", "/laporan-tim/"),
]
TIM = 40  # team members adding and inspecting the vehicles


def isi(n, mulai, orang):
    """Vehicles mulai..n-1, each with one inspection of 3 parts (one Rusak
    Berat), every second one repaired, every fifth one serviced."""
    vehicles = Vehicle.objects.bulk_create([
        Vehicle(
            nopol=f"U {i:06d}", merek="Uji", group_kendaraan="B",
            status=("siap_pakai", "perlu_servis", "dalam_perbaikan", "sudah_diperbaiki")[i % 4],
            ditambahkan_oleh=orang[i % TIM][0], penambah=orang[i % TIM][1], matra="darat",
        )
        for i in range(mulai, n)
    ])
    periksa = PemeriksaanGolonganB.objects.bulk_create([
        PemeriksaanGolonganB(
            pemeriksa=orang[i % TIM][1], vehicle=v, pembagian_kelas="A", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", km_kendaraan=10000 + i,
        )
        for i, v in enumerate(vehicles, start=mulai)
    ])
    items = PemeriksaanGolonganBItem.objects.bulk_create([
        PemeriksaanGolonganBItem(pemeriksaan=p, nomor=k, nama_alat=f"Alat {k}", kondisi=("B", "RR", "RB")[k - 1])
        for p in periksa for k in (1, 2, 3)
    ])
    PerbaikanGolonganB.objects.bulk_create([
        PerbaikanGolonganB(teknisi=orang[j % TIM][1], item=item, kondisi=("B", "RR")[j % 2], keterangan="uji")
        for j, item in enumerate(items) if item.nomor == 2 and j % 2 == 0
    ])
    Servis.objects.bulk_create([
        Servis(vehicle=v, tanggal="2026-01-15", jenis_servis="Ganti oli", bengkel="Bengkel")
        for i, v in enumerate(vehicles) if i % 5 == 0
    ])


setup_test_environment()
logging.disable(logging.CRITICAL)
runner = DiscoverRunner(verbosity=0)
lama = runner.setup_databases()
try:
    root = User.objects.create_superuser(username="uji_root", password="x")
    satuan = [Satuan.objects.create(nama=f"SATUAN UJI {i}") for i in range(10)]
    ketua = User.objects.create_user(username="uji_ketua", password="x")
    ketua.groups.add(Group.objects.get(name="Ketua Tim"))
    node = Anggota.add_root(user=ketua)
    orang = []
    for i in range(TIM):
        u = User.objects.create_user(username=f"uji_{i}", password="x")
        u.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
        AkunPublik.objects.update_or_create(user=u, defaults={"matra": "darat"})
        node.add_child(user=u)
        node.refresh_from_db()
        bio = Laporan.objects.create(akun=u, nip=str(i), nama=f"UJI {i}", pangkat="P", jabatan="J", satuan=satuan[i % 10])
        orang.append((u, bio))
    # So that "Perlu Servis" has something to work out for every vehicle.
    KmJadwal.objects.update(interval_km=5000, interval_bulan=6)

    klien = Client(HTTP_HOST="testserver")
    klien.force_login(root)
    hasil = {nama: [] for nama, _ in HALAMAN}
    sudah = 0
    for n in UKURAN:
        isi(n, sudah, orang)
        sudah = n
        for nama, url in HALAMAN:
            klien.get(url)  # warm-up: template loading, caches
            waktu = []
            for _ in range(3):
                with CaptureQueriesContext(connection) as q:
                    t = time.perf_counter()
                    r = klien.get(url)
                    waktu.append((time.perf_counter() - t) * 1000)
            assert r.status_code == 200, (url, r.status_code)
            hasil[nama].append((min(waktu), len(q)))

    lebar = max(len(nama) for nama in hasil)
    print()
    print(f"{'Halaman':{lebar}}  " + "  ".join(f"{'n=' + str(n):>16}" for n in UKURAN) + "   kali lipat per 2x data")
    for nama, baris in hasil.items():
        sel = "  ".join(f"{ms:8.0f} ms {q:3d} q" for ms, q in baris)
        rasio = [baris[i + 1][0] / baris[i][0] for i in range(len(baris) - 1) if baris[i][0] > 0]
        # Ratios of the two biggest steps: the small sizes are dominated by fixed costs.
        akhir = rasio[-1] if rasio else 0
        vonis = "tetap" if akhir < 1.3 else "linear" if akhir < 2.8 else "KUADRATIK?"
        print(f"{nama:{lebar}}  {sel}   " + " ".join(f"x{r:.1f}" for r in rasio) + f"  -> {vonis}")
    print("\n(q = jumlah query; x2 per penggandaan data = linear, x4 = kuadratik)")
finally:
    runner.teardown_databases(lama)
    teardown_test_environment()
