from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import VehicleForm
from .models import Vehicle


class VehicleModelTests(TestCase):
    def test_create_vehicle_and_str(self):
        vehicle = Vehicle.objects.create(
            nopol="B 9021 XY",
            jenis=Vehicle.Jenis.TRUK,
            merek="Hino Dutro",
            tahun=2019,
            status=Vehicle.Status.SIAP_PAKAI,
            odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )
        self.assertEqual(str(vehicle), "B 9021 XY")
        self.assertEqual(vehicle.get_jenis_display(), "Truk")
        self.assertEqual(vehicle.get_status_display(), "Siap Pakai")

    def test_nopol_must_be_unique(self):
        Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )
        with self.assertRaises(Exception):
            Vehicle.objects.create(
                nopol="B 9021 XY", jenis=Vehicle.Jenis.JEEP, merek="Jeep Wrangler",
                tahun=2020, status=Vehicle.Status.SIAP_PAKAI, odometer_km=1000,
                penanggung_jawab="Siti Amalia",
            )

    def test_default_ordering_is_by_nopol(self):
        Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )
        Vehicle.objects.create(
            nopol="B 1234 AB", jenis=Vehicle.Jenis.MOBIL, merek="Toyota Avanza",
            tahun=2021, status=Vehicle.Status.SIAP_PAKAI, odometer_km=1000,
            penanggung_jawab="Siti Amalia",
        )
        nopols = list(Vehicle.objects.values_list("nopol", flat=True))
        self.assertEqual(nopols, ["B 1234 AB", "B 9021 XY"])


class VehicleFormTests(TestCase):
    def test_valid_data_is_valid(self):
        form = VehicleForm(data={
            "nopol": "B 9021 XY",
            "jenis": Vehicle.Jenis.TRUK,
            "merek": "Hino Dutro",
            "tahun": 2019,
            "status": Vehicle.Status.SIAP_PAKAI,
            "odometer_km": 45000,
            "penanggung_jawab": "Budi Santoso",
        })
        self.assertTrue(form.is_valid())

    def test_missing_nopol_is_invalid(self):
        form = VehicleForm(data={
            "nopol": "",
            "jenis": Vehicle.Jenis.TRUK,
            "merek": "Hino Dutro",
            "tahun": 2019,
            "status": Vehicle.Status.SIAP_PAKAI,
            "odometer_km": 45000,
            "penanggung_jawab": "Budi Santoso",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("nopol", form.errors)

    def test_widgets_have_tailwind_classes(self):
        form = VehicleForm()
        self.assertIn("rounded-md", form.fields["nopol"].widget.attrs["class"])
        self.assertIn("rounded-md", form.fields["no_chasis"].widget.attrs["class"])

    def test_only_golongan_b_table_fields(self):
        self.assertEqual(
            list(VehicleForm().fields),
            ["nopol", "merek", "odometer_km", "no_chasis", "no_mesin"],
        )


class VehicleListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_redirects_when_not_authenticated(self):
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('fleet:vehicle_list')}",
        )

    def test_lists_vehicles(self):
        Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso", no_chasis="MHFXX123", no_mesin="W04DTR456",
        )
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertEqual(response.status_code, 200)
        for header in ("No. Registrasi", "Merk/ Type", "Km / Mil", "No. Chasis", "No. Mesin"):
            self.assertContains(response, header)
        self.assertContains(response, "B 9021 XY")
        self.assertContains(response, "Hino Dutro")
        self.assertContains(response, "45000")
        self.assertContains(response, "MHFXX123")
        self.assertContains(response, "W04DTR456")

    def test_empty_state(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertContains(response, "Belum ada data kendaraan.")

    def test_tambah_button_opens_modal_via_htmx(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertContains(response, f'hx-get="{reverse("fleet:vehicle_create")}"')
        self.assertContains(response, 'id="vehicle-modal-body"')

    def test_sidebar_armada_link_points_to_list(self):
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertContains(response, 'href="/armada/"')

    def test_apostrophe_in_nopol_does_not_break_confirm_js(self):
        Vehicle.objects.create(
            nopol="B 1' OR '1'='1",
            jenis=Vehicle.Jenis.MOBIL, merek="Test", tahun=2021,
            status=Vehicle.Status.SIAP_PAKAI, odometer_km=0, penanggung_jawab="Test",
        )
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        content = response.content.decode()
        # find the onsubmit attribute's JS string and confirm no raw ' survives inside it
        import re
        match = re.search(r"onsubmit=\"return confirm\('Hapus kendaraan ([^;]*?)\?'\);\"", content)
        self.assertIsNotNone(match, "onsubmit confirm() attribute not found in rendered HTML")
        js_string_content = match.group(1)
        self.assertNotIn("'", js_string_content)


class VehicleCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")

    def test_get_renders_empty_form(self):
        response = self.client.get(reverse("fleet:vehicle_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tambah Kendaraan")

    def test_post_valid_data_creates_vehicle_and_redirects(self):
        response = self.client.post(reverse("fleet:vehicle_create"), {
            "nopol": "B 1234 AB",
            "jenis": Vehicle.Jenis.MOBIL,
            "merek": "Toyota Avanza",
            "tahun": 2021,
            "status": Vehicle.Status.SIAP_PAKAI,
            "odometer_km": 1000,
            "penanggung_jawab": "Siti Amalia",
        })
        self.assertRedirects(response, reverse("fleet:vehicle_list"))
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertEqual(Vehicle.objects.first().nopol, "B 1234 AB")

    def test_post_missing_required_field_reshows_form_with_error(self):
        response = self.client.post(reverse("fleet:vehicle_create"), {
            "nopol": "",
            "jenis": Vehicle.Jenis.MOBIL,
            "merek": "Toyota Avanza",
            "tahun": 2021,
            "status": Vehicle.Status.SIAP_PAKAI,
            "odometer_km": 1000,
            "penanggung_jawab": "Siti Amalia",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.objects.count(), 0)
        self.assertContains(response, "This field is required.")

    def test_htmx_get_returns_form_partial_without_full_page(self):
        response = self.client.get(reverse("fleet:vehicle_create"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tambah Kendaraan")
        self.assertNotContains(response, "<html")

    def test_htmx_post_valid_data_returns_hx_redirect(self):
        response = self.client.post(
            reverse("fleet:vehicle_create"),
            {
                "nopol": "B 1234 AB",
                "jenis": Vehicle.Jenis.MOBIL,
                "merek": "Toyota Avanza",
                "tahun": 2021,
                "status": Vehicle.Status.SIAP_PAKAI,
                "odometer_km": 1000,
                "penanggung_jawab": "Siti Amalia",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("fleet:vehicle_list"))
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_post_duplicate_nopol_reshows_form_with_error(self):
        Vehicle.objects.create(
            nopol="B 1234 AB", jenis=Vehicle.Jenis.MOBIL, merek="Toyota Avanza",
            tahun=2021, status=Vehicle.Status.SIAP_PAKAI, odometer_km=1000,
            penanggung_jawab="Siti Amalia",
        )
        response = self.client.post(reverse("fleet:vehicle_create"), {
            "nopol": "B 1234 AB",
            "jenis": Vehicle.Jenis.MOBIL,
            "merek": "Toyota Avanza 2",
            "tahun": 2022,
            "status": Vehicle.Status.SIAP_PAKAI,
            "odometer_km": 500,
            "penanggung_jawab": "Budi Santoso",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.objects.count(), 1)
        self.assertContains(response, "already exists")


class VehicleUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )

    def test_get_renders_prefilled_form(self):
        response = self.client.get(reverse("fleet:vehicle_update", args=[self.vehicle.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Kendaraan")
        self.assertContains(response, 'value="B 9021 XY"')

    def test_htmx_get_returns_form_partial_without_full_page(self):
        response = self.client.get(
            reverse("fleet:vehicle_update", args=[self.vehicle.pk]), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Kendaraan")
        self.assertNotContains(response, "<html")

    def test_htmx_post_valid_data_returns_hx_redirect(self):
        response = self.client.post(
            reverse("fleet:vehicle_update", args=[self.vehicle.pk]),
            {
                "nopol": "B 9021 XY",
                "jenis": Vehicle.Jenis.TRUK,
                "merek": "Hino Dutro",
                "tahun": 2019,
                "status": Vehicle.Status.DALAM_PERBAIKAN,
                "odometer_km": 46000,
                "penanggung_jawab": "Budi Santoso",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], reverse("fleet:vehicle_list"))

    def test_post_updates_vehicle_and_redirects(self):
        response = self.client.post(
            reverse("fleet:vehicle_update", args=[self.vehicle.pk]),
            {
                "nopol": "B 9021 XY",
                "jenis": Vehicle.Jenis.TRUK,
                "merek": "Hino Dutro",
                "tahun": 2019,
                "status": Vehicle.Status.DALAM_PERBAIKAN,
                "odometer_km": 46000,
                "penanggung_jawab": "Budi Santoso",
                "no_chasis": "MHFXX123",
            },
        )
        self.assertRedirects(response, reverse("fleet:vehicle_list"))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.odometer_km, 46000)
        self.assertEqual(self.vehicle.no_chasis, "MHFXX123")

    def test_get_nonexistent_vehicle_returns_404(self):
        response = self.client.get(reverse("fleet:vehicle_update", args=[9999]))
        self.assertEqual(response.status_code, 404)


class VehicleDeleteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )

    def test_post_deletes_vehicle_and_redirects(self):
        response = self.client.post(reverse("fleet:vehicle_delete", args=[self.vehicle.pk]))
        self.assertRedirects(response, reverse("fleet:vehicle_list"))
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("fleet:vehicle_delete", args=[self.vehicle.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Vehicle.objects.count(), 1)
