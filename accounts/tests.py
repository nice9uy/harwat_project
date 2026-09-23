from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from fleet.models import Vehicle


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
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )
        Vehicle.objects.create(
            nopol="B 4412 KM", jenis=Vehicle.Jenis.JEEP, merek="Jeep Wrangler",
            tahun=2020, status=Vehicle.Status.DALAM_PERBAIKAN, odometer_km=30000,
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
