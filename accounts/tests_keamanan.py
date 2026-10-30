"""Hacking Activity, IP blacklist and maintenance mode (accounts.keamanan)."""
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import keamanan
from accounts.models import AktivitasMencurigakan as A
from accounts.models import IpBlokir, Pemeliharaan


class DeteksiTests(TestCase):
    def setUp(self):
        keamanan.segarkan_blokir()
        keamanan.lupakan_pemeliharaan()

    def test_attacks_are_logged(self):
        for url, jenis in (
            ("/.env", A.Jenis.PEMINDAIAN), ("/wp-login.php", A.Jenis.PEMINDAIAN),
            ("/laporan-pemeriksaan/?q=1%27%20OR%20%271%27%3D%271", A.Jenis.SQL_INJECTION),
            ("/laporan-pemeriksaan/?q=%3Cscript%3Ealert(1)%3C/script%3E", A.Jenis.XSS),
        ):
            self.client.get(url)
            self.assertTrue(A.objects.filter(jenis=jenis, path__startswith=url.split("?")[0]).exists(), url)
        self.client.get("/login/", HTTP_USER_AGENT="sqlmap/1.8")
        self.assertTrue(A.objects.filter(jenis=A.Jenis.ALAT_PERETAS).exists())

    def test_normal_use_is_not(self):
        User.objects.create_user(username="u", password="rahasia-123")
        self.client.login(username="u", password="rahasia-123")
        for url in ("/login/", "/info-profile/", "/laporan-pemeriksaan/?q=B 1234 XY&golongan=B", "/static/dist/output.css"):
            self.client.get(url)
        self.assertFalse(A.objects.exists())

    def test_failed_logins_and_admin_probing(self):
        self.client.post(reverse("accounts:login"), {"username": "siapa", "password": "salah"})
        self.assertTrue(A.objects.filter(jenis=A.Jenis.LOGIN_GAGAL).exists())
        self.client.get("/admin/")
        self.assertTrue(A.objects.filter(jenis=A.Jenis.AKSES_ADMIN).exists())

    @override_settings(KEAMANAN_BLOKIR_OTOMATIS=True)
    def test_repeated_attacks_block_the_address_then_it_is_refused(self):
        for _ in range(keamanan.BATAS_TINGGI):
            self.client.get("/.env", REMOTE_ADDR="203.0.113.9")
        blokir = IpBlokir.objects.get(alamat="203.0.113.9")
        self.assertTrue(blokir.otomatis)
        self.assertIsNotNone(blokir.sampai)
        self.assertTrue(A.objects.filter(jenis=A.Jenis.IP_DIBLOKIR, ip="203.0.113.9").exists())
        self.assertEqual(self.client.get("/login/", REMOTE_ADDR="203.0.113.9").status_code, 403)
        self.assertEqual(self.client.get("/login/", REMOTE_ADDR="203.0.113.10").status_code, 200)
        call_command("buka_blokir_ip", "203.0.113.9", stdout=open("/dev/null", "w"))
        self.assertEqual(self.client.get("/login/", REMOTE_ADDR="203.0.113.9").status_code, 200)

    def test_no_automatic_blocking_by_default(self):
        for _ in range(keamanan.BATAS_TINGGI + 2):
            self.client.get("/.env", REMOTE_ADDR="10.89.0.1")
        self.assertFalse(IpBlokir.objects.exists())
        self.assertEqual(A.objects.filter(ip="10.89.0.1").count(), keamanan.BATAS_TINGGI + 2)

    def test_a_range_is_blocked_too(self):
        IpBlokir.objects.create(alamat="198.51.100.0/24")
        keamanan.segarkan_blokir()
        self.assertEqual(self.client.get("/login/", REMOTE_ADDR="198.51.100.77").status_code, 403)


class MenuKeamananTests(TestCase):
    def setUp(self):
        keamanan.segarkan_blokir()
        keamanan.lupakan_pemeliharaan()
        self.root = User.objects.create_superuser(username="root", password="rahasia-123")

    def test_superuser_only(self):
        admin = User.objects.create_user(username="admin1", password="rahasia-123")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client.login(username="admin1", password="rahasia-123")
        self.assertNotEqual(self.client.get(reverse("accounts:keamanan")).status_code, 200)
        self.assertNotEqual(self.client.get(reverse("accounts:pemeliharaan")).status_code, 200)
        self.client.login(username="root", password="rahasia-123")
        halaman = self.client.get(reverse("accounts:keamanan"))
        self.assertContains(halaman, "Hacking Activity")
        self.assertContains(halaman, "Blacklist IP")
        self.assertContains(halaman, 'hx-trigger="sse:keamanan')

    def test_two_tabs(self):
        self.client.login(username="root", password="rahasia-123")
        aktivitas = self.client.get(reverse("accounts:keamanan"))
        self.assertContains(aktivitas, "Kejadian 24 jam")
        self.assertNotContains(aktivitas, 'name="alamat" required')
        blokir = self.client.get(reverse("accounts:keamanan"), {"tab": "blokir"})
        self.assertContains(blokir, 'name="alamat" required')
        self.assertNotContains(blokir, "Kejadian 24 jam")
        # A block from the list goes back to the Blacklist IP tab.
        kembali = self.client.post(reverse("accounts:blokir_tambah"), {"alamat": "203.0.113.5"})
        self.assertEqual(kembali["Location"], reverse("accounts:keamanan") + "?tab=blokir")

    def test_block_and_unblock_from_the_page_but_not_oneself(self):
        self.client.login(username="root", password="rahasia-123")
        self.client.post(reverse("accounts:blokir_tambah"), {"alamat": "203.0.113.0/24", "alasan": "uji"})
        self.assertTrue(IpBlokir.objects.filter(alamat="203.0.113.0/24").exists())
        self.client.post(reverse("accounts:blokir_tambah"), {"alamat": "127.0.0.1"})
        self.assertFalse(IpBlokir.objects.filter(alamat="127.0.0.1").exists())
        self.client.post(reverse("accounts:blokir_tambah"), {"alamat": "bukan-ip"})
        self.assertEqual(IpBlokir.objects.count(), 1)
        self.client.post(reverse("accounts:blokir_hapus", args=[IpBlokir.objects.get().pk]))
        self.assertFalse(IpBlokir.objects.exists())

    def test_maintenance_keeps_everyone_but_a_superuser_out(self):
        tim = User.objects.create_user(username="tim1", password="rahasia-123")
        tim.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
        self.client.login(username="root", password="rahasia-123")
        self.client.post(reverse("accounts:pemeliharaan"), {"aktif": "1", "pesan": "Pembaruan sistem"})
        self.assertTrue(Pemeliharaan.objects.get().aktif)
        self.assertEqual(self.client.get(reverse("accounts:keamanan")).status_code, 200)  # a superuser goes on
        self.client.login(username="tim1", password="rahasia-123")
        tutup = self.client.get(reverse("accounts:info_profile"))
        self.assertEqual(tutup.status_code, 503)
        self.assertContains(tutup, "Pembaruan sistem", status_code=503)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)  # the login page stays open
        Pemeliharaan.objects.update(aktif=False)
        keamanan.lupakan_pemeliharaan()
        self.client.login(username="tim1", password="rahasia-123")
        self.assertEqual(self.client.get(reverse("accounts:info_profile")).status_code, 200)


class PentestRegresiTests(TestCase):
    """Bugs found by the pentest, kept fixed."""

    def setUp(self):
        keamanan.segarkan_blokir()
        keamanan.lupakan_pemeliharaan()
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")

    def test_a_range_holding_ones_own_address_is_refused(self):
        for jaringan in ("127.0.0.0/8", "0.0.0.0/0", "::/0"):
            self.client.post(reverse("accounts:blokir_tambah"), {"alamat": jaringan})
        self.assertFalse(IpBlokir.objects.exists())
        self.assertEqual(self.client.get(reverse("accounts:keamanan")).status_code, 200)

    def test_an_impossible_maintenance_date_is_dropped_not_a_500(self):
        respon = self.client.post(reverse("accounts:pemeliharaan"), {"aktif": "0", "perkiraan_selesai": "2026-13-45T25:99"})
        self.assertEqual(respon.status_code, 302)
        self.assertIsNone(Pemeliharaan.objects.get().perkiraan_selesai)

    def test_the_bolt_api_honours_the_blacklist(self):
        from django_bolt.testing import TestClient

        from accounts.api import api

        IpBlokir.objects.create(alamat="203.0.113.50")
        keamanan.segarkan_blokir()
        with TestClient(api) as klien:
            ditolak = klien.post("/auth/login", json={"username": "root", "password": "rahasia-123"}, headers={"x-real-ip": "203.0.113.50"})
            boleh = klien.post("/auth/login", json={"username": "root", "password": "rahasia-123"}, headers={"x-real-ip": "203.0.113.51"})
        self.assertEqual(ditolak.status_code, 403)
        self.assertEqual(boleh.status_code, 200)


class AlamatBersamaTests(TestCase):
    """Rootless podman shows every visitor as the container network's gateway:
    that address must never be blocked nor lock logins for everyone."""

    def setUp(self):
        keamanan.segarkan_blokir()

    @override_settings(KEAMANAN_BLOKIR_OTOMATIS=True)
    def test_the_gateway_is_logged_but_never_blocked(self):
        for _ in range(keamanan.BATAS_TINGGI + 3):
            self.client.get("/.env", REMOTE_ADDR="10.89.0.56")
        self.assertFalse(IpBlokir.objects.exists())
        self.assertEqual(A.objects.filter(ip="10.89.0.56", jenis=A.Jenis.PEMINDAIAN).count(), keamanan.BATAS_TINGGI + 3)
        self.assertEqual(self.client.get("/login/", REMOTE_ADDR="10.89.0.56").status_code, 200)

    def test_it_cannot_be_blocked_by_hand(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        for alamat in ("10.89.0.56", "10.89.0.0/24", "10.0.0.0/8"):
            self.client.post(reverse("accounts:blokir_tambah"), {"alamat": alamat})
        self.assertFalse(IpBlokir.objects.exists())

    def test_logins_lock_per_username_only(self):
        from accounts import batas_login
        from accounts.models import GagalLogin

        for i in range(batas_login.BATAS_IP + 2):
            self.client.post(reverse("accounts:login"), {"username": f"orang{i}", "password": "salah"}, REMOTE_ADDR="10.89.0.56")
        self.assertFalse(GagalLogin.objects.filter(kunci__startswith="ip:").exists())
        User.objects.create_user(username="pegawai", password="rahasia-123")
        masuk = self.client.post(reverse("accounts:login"), {"username": "pegawai", "password": "rahasia-123"}, REMOTE_ADDR="10.89.0.56")
        self.assertEqual(masuk.status_code, 302)
