import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Laporan, PemeriksaanGolonganB, PemeriksaanGolonganBItem, RevokedToken
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
        self.assertContains(response, "x-show=\"kendaraan && kendaraan.group_kode === 'B'\"")
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
