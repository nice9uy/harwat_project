import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Laporan, RevokedToken
from fleet.models import Vehicle

# 1x1 transparent GIF — smallest valid image Pillow will accept for an
# ImageField's upload validation.
TINY_GIF = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_get_login_page(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Masuk")

    def test_login_page_defaults_to_dark_mode(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, '<html lang="id" class="dark">')
        self.assertContains(response, "localStorage.getItem('theme')")

    def test_post_valid_credentials_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "teknisi1", "password": "rahasia-123"},
        )
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_post_valid_credentials_htmx_returns_hx_redirect(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "teknisi1", "password": "rahasia-123"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/dashboard/")

    def test_post_invalid_credentials_shows_error(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "teknisi1", "password": "salah"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")

    def test_already_authenticated_user_redirects_to_dashboard(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:login"))
        self.assertRedirects(response, reverse("accounts:dashboard"))


class PasswordResetPlaceholderTests(TestCase):
    def test_placeholder_page_renders(self):
        response = self.client.get(reverse("accounts:password_reset_placeholder"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "belum tersedia")


class PengaturanViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:pengaturan')}",
        )

    def test_renders_when_authenticated(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/pengaturan/"')

    def test_shows_user_tab(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertContains(response, ">\n                User\n            </span>")

    def test_shows_user_table_with_existing_users(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertContains(response, "teknisi1")
        self.assertContains(response, "Username")
        self.assertContains(response, "Tambah User")


class UserCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")

    def test_redirects_when_not_authenticated(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:user_create"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:user_create')}",
        )

    def test_get_returns_form(self):
        response = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tambah User")

    def test_post_valid_data_creates_user(self):
        response = self.client.post(reverse("accounts:user_create"), {
            "username": "teknisi2",
            "email": "teknisi2@example.com",
            "password1": "kompleks-sekali-123",
            "password2": "kompleks-sekali-123",
        })
        self.assertRedirects(response, reverse("accounts:pengaturan"))
        self.assertTrue(User.objects.filter(username="teknisi2").exists())

    def test_post_htmx_returns_hx_redirect(self):
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "teknisi3",
                "email": "",
                "password1": "kompleks-sekali-123",
                "password2": "kompleks-sekali-123",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("accounts:pengaturan"))
        self.assertTrue(User.objects.filter(username="teknisi3").exists())

    def test_post_mismatched_passwords_shows_error(self):
        response = self.client.post(reverse("accounts:user_create"), {
            "username": "teknisi4",
            "email": "",
            "password1": "kompleks-sekali-123",
            "password2": "beda-sekali-456",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="teknisi4").exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_url_is_pemeriksaan_and_old_laporan_url_redirects(self):
        self.assertEqual(reverse("accounts:pemeriksaan"), "/pemeriksaan/")
        response = self.client.get("/laporan/")
        self.assertRedirects(response, "/pemeriksaan/", status_code=301, fetch_redirect_response=False)

    def test_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:pemeriksaan')}",
        )

    def test_renders_when_authenticated(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Form Pemeriksaan")

    def test_sidebar_link_navigates_in_same_tab(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, f'href="{reverse("accounts:pemeriksaan")}" class=')
        self.assertNotContains(response, 'target="_blank"')

    def test_jenis_pemeriksaan_has_qr_scan_button(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertContains(response, "Scan QR Code Kendaraan")
        self.assertContains(response, 'id="qr-reader"')
        self.assertContains(response, "/static/vendor/html5-qrcode.min.js")
        self.assertContains(response, reverse("fleet:vehicle_lookup"))
        for label in ("No. Registrasi", "Merk/Type", "No. Chasis", "No. Mesin", "Group Kendaraan"):
            self.assertContains(response, f">{label}</label>")

    def test_jenis_pemeriksaan_has_inspection_accordion(self):
        from .pemeriksaan import ALAT
        self.assertEqual(len(ALAT), 40)
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        for text in ("Pembagian Kelas", "Eselon Reparasi", "Macam Pemeriksaan", "Tiba-tiba"):
            self.assertContains(response, text)
        self.assertContains(response, 'name="pembagian_kelas" value="6"')
        self.assertContains(response, 'name="eselon_reparasi" value="4"')
        self.assertContains(response, 'name="macam_pemeriksaan" value="tiba_tiba"')
        self.assertContains(response, 'name="buku_jalan" value="ada"')
        self.assertContains(response, 'name="buku_jalan" value="tidak"')
        self.assertContains(response, 'id="kesatuan" name="kesatuan"')
        for no, nama in ((1, "Motor"), (20, "Gear Belakang"), (21, "Rantai"), (40, "Cat")):
            self.assertContains(response, f"{no}.</span> {nama}")
            self.assertContains(response, f'name="alat_{no}_jml"')
            # One accordion panel per part.
            self.assertContains(response, f'@click="open = open === {no} ? null : {no}"')
            self.assertContains(response, f'type="file" id="alat_{no}_foto" name="alat_{no}_foto"')
            self.assertContains(response, f'<textarea id="alat_{no}_keterangan" name="alat_{no}_keterangan"')
            for kode in ("B", "RR", "RB"):
                self.assertContains(response, f'name="alat_{no}_kondisi" value="{kode}"')

    def test_shows_all_fields(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        for field in ("nip", "nama", "pangkat", "jabatan", "satuan", "foto"):
            self.assertContains(response, f'id="id_{field}"')

    def test_shows_biodata_tab(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertContains(response, "BIODATA PEMERIKSA")
        self.assertNotContains(response, "JENIS PEMERIKSAAN")

    def _current_captcha(self):
        self.client.get(reverse("accounts:pemeriksaan"))
        return self.client.session["laporan_captcha"]

    def test_shows_captcha_code(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertContains(response, self.client.session["laporan_captcha"])

    def test_post_valid_data_creates_laporan_and_redirects(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        code = self._current_captcha()
        foto = SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif")
        response = self.client.post(reverse("accounts:pemeriksaan"), {
            "nip": "199001012015031001",
            "nama": "Budi Santoso",
            "pangkat": "Penata Muda / III-a",
            "jabatan": "Teknisi",
            "satuan": "Satuan Kerja ABC",
            "foto": foto,
            "captcha": code,
        })
        self.assertRedirects(response, reverse("accounts:pemeriksaan"))
        self.assertEqual(Laporan.objects.count(), 1)
        laporan = Laporan.objects.get()
        self.assertEqual(laporan.nip, "199001012015031001")
        self.assertEqual(laporan.nama, "Budi Santoso")

    def test_post_missing_field_shows_error_and_does_not_save(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        code = self._current_captcha()
        response = self.client.post(reverse("accounts:pemeriksaan"), {
            "nip": "199001012015031001",
            "nama": "",
            "pangkat": "Penata Muda / III-a",
            "jabatan": "Teknisi",
            "satuan": "Satuan Kerja ABC",
            "captcha": code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Laporan.objects.count(), 0)

    def test_post_wrong_captcha_shows_error_and_does_not_save(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        code = self._current_captcha()
        wrong_code = "ZZZZZZ" if code != "ZZZZZZ" else "YYYYYY"
        foto = SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif")
        response = self.client.post(reverse("accounts:pemeriksaan"), {
            "nip": "199001012015031001",
            "nama": "Budi Santoso",
            "pangkat": "Penata Muda / III-a",
            "jabatan": "Teknisi",
            "satuan": "Satuan Kerja ABC",
            "foto": foto,
            "captcha": wrong_code,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kode keamanan tidak sesuai.")
        self.assertEqual(Laporan.objects.count(), 0)

    def test_captcha_is_case_insensitive(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        code = self._current_captcha()
        foto = SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif")
        response = self.client.post(reverse("accounts:pemeriksaan"), {
            "nip": "199001012015031001",
            "nama": "Budi Santoso",
            "pangkat": "Penata Muda / III-a",
            "jabatan": "Teknisi",
            "satuan": "Satuan Kerja ABC",
            "foto": foto,
            "captcha": code.lower(),
        })
        self.assertRedirects(response, reverse("accounts:pemeriksaan"))
        self.assertEqual(Laporan.objects.count(), 1)


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_dashboard_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:dashboard')}",
        )

    def test_dashboard_renders_all_four_blocks_when_authenticated(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ringkasan Armada")
        self.assertContains(response, "Jadwal Perawatan Mendatang")
        self.assertContains(response, "Alert Overdue")
        self.assertContains(response, "Aktivitas Terbaru")

    def test_dashboard_has_theme_toggle(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, 'aria-label="Ganti tema"')

    def test_dashboard_shows_mock_fleet_counts(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Truk Angkut B 9021 XY")
        self.assertContains(response, "Servis berkala lewat 12 hari")
        self.assertContains(response, "Budi Santoso")

    def test_dashboard_shows_real_fleet_summary_counts(self):
        Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI,
            penanggung_jawab="Budi Santoso",
        )
        Vehicle.objects.create(
            nopol="B 4412 KM", jenis=Vehicle.Jenis.JEEP, merek="Jeep Wrangler",
            tahun=2020, status=Vehicle.Status.DALAM_PERBAIKAN,
            penanggung_jawab="Siti Amalia",
        )
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.context["fleet_summary"]["total"], 2)
        self.assertEqual(response.context["fleet_summary"]["ready"], 1)
        self.assertEqual(response.context["fleet_summary"]["in_repair"], 1)
        self.assertEqual(response.context["fleet_summary"]["due_soon"], 0)

    def test_dashboard_shows_zero_fleet_summary_when_no_vehicles(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.context["fleet_summary"]["total"], 0)
        self.assertEqual(response.context["fleet_summary"]["ready"], 0)
        self.assertEqual(response.context["fleet_summary"]["in_repair"], 0)
        self.assertEqual(response.context["fleet_summary"]["due_soon"], 0)

    def test_dashboard_polls_for_updates(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, 'hx-trigger="every 10s"')
        self.assertContains(response, f'hx-get="{reverse("accounts:dashboard_partial")}"')


class DashboardPartialViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("accounts:dashboard_partial"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:dashboard_partial')}",
        )

    def test_returns_fragment_with_fresh_fleet_summary(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI,
            penanggung_jawab="Budi Santoso",
        )
        response = self.client.get(reverse("accounts:dashboard_partial"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["fleet_summary"]["total"], 1)
        self.assertContains(response, "Ringkasan Armada")
        self.assertNotContains(response, "<!DOCTYPE")


class RevokedTokenModelTests(TestCase):
    def test_create_and_query_by_jti(self):
        RevokedToken.objects.create(
            jti="abc123", expires_at=timezone.now() + timezone.timedelta(days=7)
        )
        self.assertTrue(RevokedToken.objects.filter(jti="abc123").exists())

    def test_jti_must_be_unique(self):
        expires = timezone.now() + timezone.timedelta(days=7)
        RevokedToken.objects.create(jti="dup", expires_at=expires)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RevokedToken.objects.create(jti="dup", expires_at=expires)


class FormTambahViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("accounts:form_tambah"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:form_tambah')}",
        )

    def test_renders_when_authenticated(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:form_tambah"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Form Tambah")
        self.assertContains(response, "BIODATA")
        self.assertContains(response, "TAMBAH KENDARAAN")
        self.assertContains(response, 'type="radio" name="golongan" value="B"')
        self.assertContains(response, 'Golongan "B"')
        for field in ("nip", "nama", "pangkat", "jabatan", "satuan", "foto"):
            self.assertContains(response, f'id="id_{field}"')

    def test_sidebar_brand_has_kemhan_logo(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, 'src="/static/img/kemhan_logo.png" alt="Logo Kementerian Pertahanan"')

    def test_sidebar_link_below_form_laporan(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        content = self.client.get(reverse("accounts:dashboard")).content.decode()
        self.assertLess(
            content.index(f'href="{reverse("accounts:pemeriksaan")}"'),
            content.index(f'href="{reverse("accounts:form_tambah")}"'),
        )
