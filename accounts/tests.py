import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Laporan,
    PemeriksaanBermotor,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanBermotor,
    PerbaikanGolonganB,
    RevokedToken,
)
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
            "keanggotaan": "tim_pemeriksaan",
        })
        self.assertRedirects(response, reverse("accounts:pengaturan"))
        user = User.objects.get(username="teknisi2")
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["Tim Pemeriksaan"])
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_post_htmx_returns_hx_redirect(self):
        response = self.client.post(
            reverse("accounts:user_create"),
            {
                "username": "teknisi3",
                "keanggotaan": "pimpinan",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("accounts:pengaturan"))
        self.assertTrue(User.objects.filter(username="teknisi3").exists())

    def _create(self, keanggotaan):
        return self.client.post(reverse("accounts:user_create"), {
            "username": "baru",
            "keanggotaan": keanggotaan,
        })

    def test_keanggotaan_is_required(self):
        response = self._create("")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="baru").exists())

    def test_admin_gets_group_and_staff(self):
        self._create("admin")
        user = User.objects.get(username="baru")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.groups.filter(name="Admin").exists())

    def test_non_superuser_cannot_create_superuser(self):
        response = self.client.get(reverse("accounts:user_create"))
        self.assertNotContains(response, 'value="superuser"')
        self._create("superuser")
        self.assertFalse(User.objects.filter(username="baru").exists())

    def test_superuser_can_create_superuser(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertContains(self.client.get(reverse("accounts:user_create")), 'value="superuser"')
        self._create("superuser")
        user = User.objects.get(username="baru")
        self.assertTrue(user.is_superuser and user.is_staff)

    def test_pengaturan_lists_keanggotaan(self):
        self._create("tim_perbaikan")
        User.objects.create_superuser(username="root", password="rahasia-123")
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertContains(response, "<th class=\"py-2 px-4 font-medium\">Keanggotaan</th>", html=True)
        self.assertContains(response, "Tim Perbaikan")
        self.assertContains(response, "Superuser")

    def test_all_role_groups_exist(self):
        from django.contrib.auth.models import Group

        from accounts.roles import GROUP_NAMES
        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)) & set(GROUP_NAMES.values()),
            {"Admin", "Pimpinan", "Tim Pemeriksaan", "Tim Penambahan Data", "Tim Perbaikan"},
        )

    def test_new_user_gets_default_password_and_no_email_field(self):
        response = self.client.get(reverse("accounts:user_create"))
        self.assertNotContains(response, 'name="email"')
        self.assertNotContains(response, 'name="password1"')
        self.assertContains(response, "Password awal user baru")
        self._create("tim_perbaikan")
        self.assertTrue(User.objects.get(username="baru").check_password("12345"))

    def test_duplicate_username_is_rejected(self):
        self._create("tim_perbaikan")
        response = self._create("tim_perbaikan")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="baru").count(), 1)


def _pemeriksaan_data(vehicle, **overrides):
    """POST fields of the PEMERIKSAAN tab for a fully filled-in inspection."""
    data = {
        "vehicle": vehicle.pk,
        "pembagian_kelas": "2",
        "eselon_reparasi": "3",
        "macam_pemeriksaan": "tehnis",
        "buku_jalan": "ada",
        "kesatuan": "Yonif Mekanis 202/TM",
    }
    for nomor in range(1, 41):
        data[f"alat_{nomor}_kondisi"] = "B"
        data[f"alat_{nomor}_jml"] = "1"
    data.update(overrides)
    return data


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro")

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
        self.assertContains(response, 'readonly tabindex="-1"', count=5)
        self.assertContains(response, 'id="pemeriksaan-lanjutkan"')

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
            **_pemeriksaan_data(self.vehicle),
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
            **_pemeriksaan_data(self.vehicle),
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
            **_pemeriksaan_data(self.vehicle),
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
            **_pemeriksaan_data(self.vehicle),
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


class HistoryPerbaikanMenuTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_pages_require_login(self):
        for name in ("history", "perbaikan"):
            url = reverse(f"accounts:{name}")
            self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_pages_render(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        self.assertContains(self.client.get(reverse("accounts:history")), "<title>History — BMN Harwat</title>", html=True)
        self.assertContains(self.client.get(reverse("accounts:perbaikan")), "<title>Perbaikan — BMN Harwat</title>", html=True)

    def test_perbaikan_has_biodata_and_perbaikan_tabs(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("accounts:perbaikan"))
        self.assertContains(response, "BIODATA")
        self.assertContains(response, "PERBAIKAN\n")
        for field in ("nip", "nama", "pangkat", "jabatan", "satuan", "foto"):
            self.assertContains(response, f'id="id_{field}"')
        self.assertContains(response, "Lanjut")

    def test_sidebar_order_after_form_tambah(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        content = self.client.get(reverse("accounts:dashboard")).content.decode()
        positions = [
            content.index(f'href="{reverse(f"accounts:{name}")}"')
            for name in ("form_tambah", "history", "perbaikan", "pengaturan")
        ]
        self.assertEqual(positions, sorted(positions))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PemeriksaanGolonganBSaveTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro")

    def _post(self, **overrides):
        self.client.get(reverse("accounts:pemeriksaan"))
        data = {
            "nip": "199001012015031001",
            "nama": "Budi Santoso",
            "pangkat": "Kapten",
            "jabatan": "Teknisi",
            "satuan": "Satuan Kerja ABC",
            "foto": SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif"),
            "captcha": self.client.session["laporan_captcha"],
            **_pemeriksaan_data(self.vehicle),
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:pemeriksaan"), data)

    def test_saves_inspection_linked_to_vehicle_and_pemeriksa(self):
        response = self._post(
            alat_1_kondisi="RB", alat_1_jml="2", alat_1_keterangan="Bocor oli",
            alat_1_foto=SimpleUploadedFile("motor.gif", TINY_GIF, content_type="image/gif"),
            alat_40_jml="",
        )
        self.assertRedirects(response, reverse("accounts:pemeriksaan"))
        hasil = PemeriksaanGolonganB.objects.get()
        self.assertEqual(hasil.vehicle, self.vehicle)
        self.assertEqual(hasil.pemeriksa, Laporan.objects.get())
        self.assertEqual(
            (hasil.pembagian_kelas, hasil.eselon_reparasi, hasil.macam_pemeriksaan, hasil.buku_jalan, hasil.kesatuan),
            ("2", "3", "tehnis", "ada", "Yonif Mekanis 202/TM"),
        )
        self.assertEqual(hasil.items.count(), 40)
        motor = hasil.items.get(nomor=1)
        self.assertEqual((motor.nama_alat, motor.kondisi, motor.jumlah, motor.keterangan), ("Motor", "RB", 2, "Bocor oli"))
        self.assertTrue(motor.foto.name.startswith("pemeriksaan/") and motor.foto.name.endswith(".jpg"))
        cat = hasil.items.get(nomor=40)
        self.assertEqual((cat.nama_alat, cat.jumlah, cat.foto.name), ("Cat", None, ""))

    def test_missing_item_kondisi_saves_nothing(self):
        response = self._post(alat_17_kondisi="")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kondisi 17. Ban Depan belum dipilih.")
        self.assertEqual(Laporan.objects.count(), 0)
        self.assertEqual(PemeriksaanGolonganB.objects.count(), 0)

    def test_without_scanned_vehicle_is_rejected(self):
        response = self._post(vehicle="")
        self.assertContains(response, "Scan QR Code kendaraan terlebih dahulu.")
        self.assertEqual(PemeriksaanGolonganB.objects.count(), 0)

    def test_vehicle_outside_golongan_b_is_rejected(self):
        Vehicle.objects.filter(pk=self.vehicle.pk).update(group_kendaraan="X")
        self._post()
        self.assertEqual(PemeriksaanGolonganB.objects.count(), 0)

    def test_vehicle_with_inspection_cannot_be_deleted(self):
        self._post()
        response = self.client.post(reverse("fleet:vehicle_delete", args=[self.vehicle.pk]), follow=True)
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())
        self.assertContains(response, "tidak bisa dihapus karena sudah punya data pemeriksaan")

    def test_form_marks_classification_and_kondisi_required(self):
        response = self.client.get(reverse("accounts:pemeriksaan"))
        for name in ("pembagian_kelas", "eselon_reparasi", "macam_pemeriksaan", "buku_jalan", "alat_40_kondisi"):
            self.assertRegex(response.content.decode(), rf'name="{name}" value="[^"]+"[^>]*required')
        self.assertContains(response, 'name="vehicle"')


class PemeriksaanCaptchaCheckTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.client.get(reverse("accounts:pemeriksaan"))
        self.url = reverse("accounts:pemeriksaan_captcha")

    def test_correct_code_is_ok_and_keeps_code_for_the_real_submit(self):
        code = self.client.session["laporan_captcha"]
        response = self.client.post(self.url, {"captcha": code.lower()})
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(self.client.session["laporan_captcha"], code)

    def test_wrong_code_is_rejected_without_reload(self):
        response = self.client.post(self.url, {"captcha": "XXXXXX"})
        self.assertEqual(response.json(), {"ok": False, "error": "Kode keamanan tidak sesuai."})

    def test_code_rotates_after_five_wrong_attempts(self):
        old = self.client.session["laporan_captcha"]
        for _ in range(4):
            self.client.post(self.url, {"captcha": "XXXXXX"})
        data = self.client.post(self.url, {"captcha": "XXXXXX"}).json()
        self.assertFalse(data["ok"])
        self.assertNotEqual(data["code"], old)
        self.assertEqual(self.client.session["laporan_captcha"], data["code"])

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_modal_uses_precheck_and_golongan_b_form_is_group_specific(self):
        response = self.client.get(reverse("accounts:pemeriksaan"))
        self.assertContains(response, self.url)
        self.assertContains(response, '@click="kirim()"')
        self.assertRegex(response.content.decode(), r'<button type="button" @click="kirim\(\)"[^>]*>Konfirmasi &amp; Kirim</button>')
        self.assertContains(response, "<template x-if=\"kendaraan && kendaraan.group_kode === 'B'\">")
        self.assertContains(response, "<template x-if=\"kendaraan && kendaraan.group_kode === 'bermotor'\">")
        self.assertContains(response, "belum tersedia.")


class HistoryScanTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro")

    def _inspection(self, rusak_berat=0):
        pemeriksa = Laporan.objects.create(
            nip="1", nama="Budi Santoso", pangkat="Kapten", jabatan="Teknisi", satuan="ABC", foto="laporan/x.gif",
        )
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, pembagian_kelas="2", eselon_reparasi="3",
            macam_pemeriksaan="tehnis", buku_jalan="ada",
        )
        for nomor in range(1, 41):
            PemeriksaanGolonganBItem.objects.create(
                pemeriksaan=hasil, nomor=nomor, nama_alat=f"Alat {nomor}",
                kondisi="RB" if nomor <= rusak_berat else "B",
            )
        return hasil

    def test_history_page_has_scan_button(self):
        response = self.client.get(reverse("accounts:history"))
        self.assertContains(response, "Scan QR Code Kendaraan")
        self.assertContains(response, 'id="qr-reader"')
        self.assertContains(response, reverse("accounts:history_kendaraan"))
        self.assertContains(response, "/static/js/qr-scan.js")

    def test_scanned_vehicle_shows_its_inspections(self):
        self._inspection(rusak_berat=3)
        response = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertContains(response, "Budi Santoso (Kapten)")
        self.assertContains(response, "B 37")
        self.assertContains(response, "RB 3")
        self.assertContains(response, "Kelas 2 · Eselon 3 · Tehnis")

    def test_history_page_has_four_tabs(self):
        response = self.client.get(reverse("accounts:history"))
        for label in ("PROFILE", "STATUS KENDARAAN", "RIWAYAT PEMERIKSAAN", "RIWAYAT PERBAIKAN"):
            self.assertContains(response, label)
        # The scan button lives in the PROFILE tab only.
        self.assertRegex(
            response.content.decode(),
            r"<div x-show=\"tab === 'profile'\" class=\"space-y-4\">\s*<button type=\"button\" @click=\"startScan\(\)\"",
        )
        self.assertContains(response, "Scan QR Code kendaraan di tab")

    def test_scanned_vehicle_fills_every_tab(self):
        self._inspection(rusak_berat=2)
        response = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 9021 XY"})
        for panel in ("profile", "status", "pemeriksaan", "perbaikan"):
            self.assertContains(response, f"x-show=\"tab === '{panel}'\"")
        # Profile
        self.assertContains(response, reverse("fleet:vehicle_qr", args=[self.vehicle.pk]))
        self.assertContains(response, "Golongan B")
        # Status: vehicle status and the parts not in good condition
        self.assertContains(response, "Siap Pakai")
        self.assertContains(response, "Perlu Perhatian (2)")
        # Each part needing attention is an accordion with its damage details.
        self.assertContains(response, '@click="buka = buka === 1 ? null : 1"')
        self.assertContains(response, "Rusak Berat")
        self.assertContains(response, "Tidak ada foto.")
        self.assertContains(response, "1. Alat 1")
        self.assertNotContains(response, "3. Alat 3")
        # Perbaikan
        self.assertContains(response, "Belum ada riwayat perbaikan untuk kendaraan ini.")

    def test_vehicle_without_inspections(self):
        response = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertContains(response, "Belum ada riwayat pemeriksaan untuk kendaraan ini.")

    def test_unknown_vehicle(self):
        response = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "Z 1 ZZ"})
        self.assertContains(response, "Kendaraan tidak ditemukan.")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertEqual(response.status_code, 302)


class PerbaikanScanTests(HistoryScanTests):
    """Reuses HistoryScanTests' setup and _inspection helper."""

    def test_perbaikan_tab_has_scan_button(self):
        response = self.client.get(reverse("accounts:perbaikan"))
        self.assertContains(response, "Scan QR Code Kendaraan")
        self.assertContains(response, 'id="qr-reader"')
        self.assertContains(response, reverse("accounts:perbaikan_kendaraan"))

    def test_lists_parts_to_repair_from_latest_inspection(self):
        self._inspection(rusak_berat=5)
        self._inspection(rusak_berat=2)
        response = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertContains(response, "Item yang Harus Diperbaiki (2)")
        self.assertContains(response, "2. Alat 2")
        self.assertNotContains(response, "3. Alat 3")
        self.assertContains(response, '@click="buka = buka === 1 ? null : 1"')

    def test_vehicle_never_inspected(self):
        response = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertContains(response, "belum pernah diperiksa")

    def test_unknown_vehicle_and_login(self):
        response = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "Z 1 ZZ"})
        self.assertContains(response, "Kendaraan tidak ditemukan.")
        self.client.logout()
        response = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertEqual(response.status_code, 302)



@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PerbaikanSaveTests(HistoryScanTests):
    """Reuses HistoryScanTests' setup and _inspection helper."""

    def _post(self, **fields):
        data = {
            "nip": "2", "nama": "Andi Teknisi", "pangkat": "Serka", "jabatan": "Mekanik", "satuan": "Bengkel",
            "foto": SimpleUploadedFile("teknisi.gif", TINY_GIF, content_type="image/gif"),
            "vehicle": self.vehicle.pk,
        }
        data.update(fields)
        return self.client.post(reverse("accounts:perbaikan"), data)

    def _daftar(self):
        return self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 9021 XY"})

    def test_each_item_has_perbaikan_button_and_fields(self):
        hasil = self._inspection(rusak_berat=1)
        item = hasil.items.get(nomor=1)
        response = self._daftar()
        self.assertContains(response, "Batal Perbaikan")
        for suffix in ("aktif", "jml", "keterangan", "foto"):
            self.assertContains(response, f'name="perbaikan_{item.pk}_{suffix}"')
        self.assertContains(response, f'name="perbaikan_{item.pk}_kondisi" value="B"')
        self.assertContains(response, 'id="simpan-perbaikan"')

    def test_repaired_to_baik_disappears_from_list(self):
        hasil = self._inspection(rusak_berat=2)
        motor = hasil.items.get(nomor=1)
        response = self._post(**{
            f"perbaikan_{motor.pk}_aktif": "1",
            f"perbaikan_{motor.pk}_kondisi": "B",
            f"perbaikan_{motor.pk}_jml": "1",
            f"perbaikan_{motor.pk}_keterangan": "Ganti gasket",
            f"perbaikan_{motor.pk}_foto": SimpleUploadedFile("after.gif", TINY_GIF, content_type="image/gif"),
        })
        self.assertRedirects(response, reverse("accounts:perbaikan") + "?nopol=B+9021+XY")
        perbaikan = PerbaikanGolonganB.objects.get()
        self.assertEqual((perbaikan.item, perbaikan.kondisi, perbaikan.jumlah), (motor, "B", 1))
        self.assertEqual(perbaikan.teknisi.nama, "Andi Teknisi")
        self.assertTrue(perbaikan.foto.name.startswith("perbaikan/"))
        daftar = self._daftar()
        self.assertContains(daftar, "Item yang Harus Diperbaiki (1)")
        self.assertNotContains(daftar, "1. Alat 1")
        self.assertContains(daftar, "2. Alat 2")
        # History reflects it too.
        history = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 9021 XY"})
        self.assertContains(history, "Perlu Perhatian (1)")
        self.assertContains(history, "Teknisi: Andi Teknisi (Serka)")
        self.assertContains(history, "Ganti gasket")

    def test_repair_still_rusak_stays_on_list(self):
        hasil = self._inspection(rusak_berat=1)
        motor = hasil.items.get(nomor=1)
        self._post(**{f"perbaikan_{motor.pk}_aktif": "1", f"perbaikan_{motor.pk}_kondisi": "RR"})
        daftar = self._daftar()
        self.assertContains(daftar, "1. Alat 1")
        self.assertContains(daftar, "masih rusak ringan")

    def test_inactive_items_are_ignored_and_one_is_required(self):
        hasil = self._inspection(rusak_berat=1)
        motor = hasil.items.get(nomor=1)
        response = self._post(**{f"perbaikan_{motor.pk}_kondisi": "B"})
        self.assertContains(response, "Pilih minimal satu item")
        self.assertEqual(PerbaikanGolonganB.objects.count(), 0)

    def test_missing_kondisi_saves_nothing(self):
        hasil = self._inspection(rusak_berat=1)
        motor = hasil.items.get(nomor=1)
        response = self._post(**{f"perbaikan_{motor.pk}_aktif": "1"})
        self.assertContains(response, "Kondisi perbaikan 1. Alat 1 belum dipilih.")
        self.assertEqual(PerbaikanGolonganB.objects.count(), 0)
        self.assertEqual(Laporan.objects.filter(nama="Andi Teknisi").count(), 0)

    def test_item_not_needing_repair_cannot_be_posted(self):
        hasil = self._inspection(rusak_berat=0)
        good = hasil.items.get(nomor=1)
        response = self._post(**{f"perbaikan_{good.pk}_aktif": "1", f"perbaikan_{good.pk}_kondisi": "B"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PerbaikanGolonganB.objects.count(), 0)



class TemplateCommentTests(TestCase):
    def test_no_multiline_hash_comments(self):
        """Django's {# #} is single-line only; a multi-line one renders as page text."""
        from pathlib import Path

        from django.conf import settings

        offenders = []
        for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{number}")
        self.assertEqual(offenders, [], "Use {% comment %} for multi-line template comments")



class UserDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="operator", password="rahasia-123")
        self.client.login(username="operator", password="rahasia-123")
        self.target = User.objects.create_user(username="teknisi9", password="x")
        self.root = User.objects.create_superuser(username="root", password="rahasia-123")

    def test_table_has_number_and_action_columns(self):
        response = self.client.get(reverse("accounts:pengaturan"))
        self.assertContains(response, '<th class="py-2 px-4 font-medium w-12">No</th>', html=True)
        self.assertContains(response, '<th class="py-2 px-4 font-medium">Aksi</th>', html=True)
        self.assertContains(response, f'hx-get="{reverse("accounts:user_delete", args=[self.target.pk])}"')
        self.assertNotContains(response, reverse("accounts:user_delete", args=[self.root.pk]))
        self.assertNotContains(response, reverse("accounts:user_delete", args=[self.admin.pk]))

    def test_confirm_then_delete(self):
        url = reverse("accounts:user_delete", args=[self.target.pk])
        self.assertContains(self.client.get(url), "Yakin ingin menghapus user")
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, reverse("accounts:pengaturan"))
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    def test_superuser_cannot_be_deleted(self):
        response = self.client.post(reverse("accounts:user_delete", args=[self.root.pk]), follow=True)
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())
        self.assertContains(response, "User root tidak bisa dihapus.")

    def test_cannot_delete_own_account(self):
        self.client.post(reverse("accounts:user_delete", args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_requires_login(self):
        self.client.logout()
        self.client.post(reverse("accounts:user_delete", args=[self.target.pk]))
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())



class MenuAccessTests(TestCase):
    def _login_as(self, keanggotaan):
        from django.contrib.auth.models import Group

        from accounts.roles import GROUP_NAMES
        user = User.objects.create_user(username=keanggotaan, password="rahasia-123")
        user.groups.add(Group.objects.get(name=GROUP_NAMES[keanggotaan]))
        self.client.login(username=keanggotaan, password="rahasia-123")
        return user

    def _sidebar_menus(self, response):
        content = response.content.decode()
        names = {
            "dashboard": "accounts:dashboard", "armada": "fleet:vehicle_list",
            "pemeriksaan": "accounts:pemeriksaan", "form_tambah": "accounts:form_tambah",
            "history": "accounts:history", "perbaikan": "accounts:perbaikan",
            "pengaturan": "accounts:pengaturan",
        }
        return {menu for menu, name in names.items() if f'<a href="{reverse(name)}" class=' in content}

    def _check(self, keanggotaan, allowed, home):
        self._login_as(keanggotaan)
        response = self.client.get(reverse(home))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._sidebar_menus(response), allowed)
        self.assertNotContains(response, "Jadwal")
        # Other menus redirect back home, even when typed as a URL.
        for name in ("accounts:dashboard", "fleet:vehicle_list", "accounts:pengaturan",
                     "accounts:pemeriksaan", "accounts:form_tambah", "accounts:perbaikan"):
            if name != home:
                response = self.client.get(reverse(name))
                if name.split(":")[1] in ("pemeriksaan", "form_tambah", "perbaikan") and name.split(":")[1] in allowed:
                    self.assertEqual(response.status_code, 200, name)
                else:
                    self.assertRedirects(response, reverse(home), msg_prefix=name)
        self.assertEqual(self.client.get(reverse("accounts:history")).status_code, 200)

    def test_tim_pemeriksaan(self):
        self._check("tim_pemeriksaan", {"pemeriksaan", "history"}, "accounts:pemeriksaan")

    def test_tim_penambahan_data(self):
        self._check("tim_penambahan_data", {"form_tambah", "history"}, "accounts:form_tambah")

    def test_tim_perbaikan(self):
        self._check("tim_perbaikan", {"perbaikan", "history"}, "accounts:perbaikan")

    def test_tim_login_lands_on_first_menu(self):
        User.objects.create_user(username="p", password="rahasia-123").groups.add(
            __import__("django.contrib.auth.models", fromlist=["Group"]).Group.objects.get(name="Tim Perbaikan")
        )
        response = self.client.post(reverse("accounts:login"), {"username": "p", "password": "rahasia-123"})
        self.assertRedirects(response, reverse("accounts:perbaikan"))

    def test_scan_endpoints_follow_menu(self):
        self._login_as("tim_perbaikan")
        self.assertEqual(self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "x"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "x"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("fleet:vehicle_lookup"), {"nopol": "x"}).status_code, 302)

    def test_admin_and_pimpinan_see_everything(self):
        for keanggotaan in ("admin", "pimpinan"):
            self.client.logout()
            self._login_as(keanggotaan)
            response = self.client.get(reverse("accounts:dashboard"))
            self.assertEqual(
                self._sidebar_menus(response),
                {"dashboard", "armada", "pemeriksaan", "form_tambah", "history", "perbaikan", "pengaturan"},
            )


class SidebarLogoutTests(TestCase):
    def test_keluar_is_at_the_bottom_of_the_sidebar(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        content = self.client.get(reverse("accounts:dashboard")).content.decode()
        button = content.index('@click="logoutOpen = true"')
        self.assertLess(content.index("</nav>"), button)
        self.assertLess(button, content.index("</aside>"))
        # The button only opens a confirmation; the logout form lives in that modal.
        logout_form = content.index(f'action="{reverse("accounts:logout")}"')
        self.assertLess(content.index('x-show="logoutOpen"'), logout_form)
        self.assertEqual(content.count(f'action="{reverse("accounts:logout")}"'), 1)
        self.assertContains(self.client.get(reverse("accounts:dashboard")), "Yakin ingin keluar dari aplikasi?")



def _bermotor_data(vehicle, **overrides):
    """POST fields of the PEMERIKSAAN tab for a filled-in Kendaraan Bermotor inspection."""
    data = {
        "vehicle": vehicle.pk,
        "bbm": "Solar",
        "buku_harian": "ada",
        "macam_pemeriksaan": "tiba_tiba",
        "tempat_pemeriksaan": "Bengkel 202",
    }
    for nomor in range(1, 64):
        data[f"alat_{nomor}_kondisi"] = "B"
    data.update(overrides)
    return data


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PemeriksaanBermotorTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(nopol="B 7777 KB", merek="Toyota Hilux", group_kendaraan="bermotor")

    def _biodata(self, nama="Budi Santoso"):
        return {
            "nip": "1", "nama": nama, "pangkat": "Kapten", "jabatan": "Teknisi", "satuan": "ABC",
            "foto": SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif"),
        }

    def _post_pemeriksaan(self, **overrides):
        self.client.get(reverse("accounts:pemeriksaan"))
        return self.client.post(reverse("accounts:pemeriksaan"), {
            **self._biodata(),
            "captcha": self.client.session["laporan_captcha"],
            **_bermotor_data(self.vehicle, **overrides),
        })

    def test_page_has_bermotor_checklist(self):
        from accounts.pemeriksaan import KOMPONEN_BERMOTOR
        self.assertEqual(len(KOMPONEN_BERMOTOR), 63)
        response = self.client.get(reverse("accounts:pemeriksaan"))
        for text in ("BBM, Buku Harian, Macam &amp; Tempat Pemeriksaan", 'name="bbm"', 'name="tempat_pemeriksaan"',
                     'name="buku_harian" value="ada"', "1.</span> Mesin / Tune Up / Over Haul", "63.</span> Winch",
                     'name="alat_63_kondisi" value="TA"', "Harus Diperbaiki", "Harus Diganti", "Tidak Ada"):
            self.assertContains(response, text)

    def test_saves_bermotor_inspection(self):
        response = self._post_pemeriksaan(alat_1_kondisi="HP", alat_60_kondisi="TA", alat_1_keterangan="Tune up")
        self.assertRedirects(response, reverse("accounts:pemeriksaan"))
        hasil = PemeriksaanBermotor.objects.get()
        self.assertEqual((hasil.vehicle, hasil.bbm, hasil.buku_harian, hasil.macam_pemeriksaan, hasil.tempat_pemeriksaan),
                         (self.vehicle, "Solar", "ada", "tiba_tiba", "Bengkel 202"))
        self.assertEqual(hasil.items.count(), 63)
        self.assertEqual(hasil.items.get(nomor=60).nama_alat, "Dongkrak")
        self.assertEqual(PemeriksaanGolonganB.objects.count(), 0)

    def test_golongan_b_kondisi_code_rejected_for_bermotor(self):
        response = self._post_pemeriksaan(alat_5_kondisi="RR")
        self.assertContains(response, "Kondisi 5. Noken As, Rocker Arm belum dipilih.")
        self.assertEqual(PemeriksaanBermotor.objects.count(), 0)

    def test_history_and_perbaikan_for_bermotor(self):
        self._post_pemeriksaan(alat_1_kondisi="HP", alat_2_kondisi="HG", alat_60_kondisi="TA")
        history = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 7777 KB"})
        for text in ("HP 1", "HG 1", "TA 1", "B 60", "Tiba-tiba · Buku harian ada · BBM Solar · Bengkel 202",
                     "Perlu Perhatian (3)"):
            self.assertContains(history, text)

        daftar = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 7777 KB"})
        self.assertContains(daftar, "Item yang Harus Diperbaiki (3)")
        mesin = PemeriksaanBermotor.objects.get().items.get(nomor=1)
        self.assertContains(daftar, f'name="perbaikan_{mesin.pk}_kondisi" value="HG"')

        response = self.client.post(reverse("accounts:perbaikan"), {
            **self._biodata("Andi Teknisi"),
            "vehicle": self.vehicle.pk,
            f"perbaikan_{mesin.pk}_aktif": "1",
            f"perbaikan_{mesin.pk}_kondisi": "B",
        })
        self.assertRedirects(response, reverse("accounts:perbaikan") + "?nopol=B+7777+KB")
        self.assertEqual(PerbaikanBermotor.objects.get().item, mesin)
        daftar = self.client.get(reverse("accounts:perbaikan_kendaraan"), {"nopol": "B 7777 KB"})
        self.assertContains(daftar, "Item yang Harus Diperbaiki (2)")
        history = self.client.get(reverse("accounts:history_kendaraan"), {"nopol": "B 7777 KB"})
        self.assertContains(history, "Teknisi: Andi Teknisi")

    def test_vehicle_with_bermotor_inspection_cannot_be_deleted(self):
        self._post_pemeriksaan()
        self.client.post(reverse("fleet:vehicle_delete", args=[self.vehicle.pk]))
        self.assertTrue(Vehicle.objects.filter(pk=self.vehicle.pk).exists())
