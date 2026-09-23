import io
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from django.urls import reverse

from .forms import VehicleForm
from .models import Vehicle, VehiclePhoto

MEDIA_ROOT = tempfile.mkdtemp()


def _png_upload(name="mobil.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def _photos(count=4):
    return [_png_upload(f"mobil-{i}.png") for i in range(count)]


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
        }, files={"foto": _photos()})
        self.assertTrue(form.is_valid(), form.errors)

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
            ["nopol", "merek", "odometer_km", "no_chasis", "no_mesin", "foto"],
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
        for header in ("No. Registrasi", "Merk/ Type", "No. Chasis", "No. Mesin"):
            self.assertContains(response, header)
        self.assertContains(response, "B 9021 XY")
        self.assertContains(response, "Hino Dutro")
        self.assertNotContains(response, "Km / Mil")
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

    def test_delete_confirm_modal_escapes_nopol(self):
        vehicle = Vehicle.objects.create(nopol="B 1' <b>X</b>", merek="Test", odometer_km=0)
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_delete_confirm", args=[vehicle.pk]))
        self.assertContains(response, "B 1&#x27; &lt;b&gt;X&lt;/b&gt;")
        self.assertNotContains(response, "<b>X</b>")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
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
            "foto": _photos(),
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
                "foto": _photos(),
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


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class VehicleUpdateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        self.vehicle = Vehicle.objects.create(
            nopol="B 9021 XY", jenis=Vehicle.Jenis.TRUK, merek="Hino Dutro",
            tahun=2019, status=Vehicle.Status.SIAP_PAKAI, odometer_km=45000,
            penanggung_jawab="Budi Santoso",
        )
        for upload in _photos():
            VehiclePhoto.objects.create(vehicle=self.vehicle, image=upload)

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


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
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

    def test_list_hapus_opens_confirm_modal_instead_of_js_confirm(self):
        response = self.client.get(reverse("fleet:vehicle_list"))
        url = reverse("fleet:vehicle_delete_confirm", args=[self.vehicle.pk])
        self.assertContains(response, f'hx-get="{url}"', count=2)
        self.assertNotContains(response, "confirm(")

    def test_confirm_modal_posts_to_delete(self):
        response = self.client.get(reverse("fleet:vehicle_delete_confirm", args=[self.vehicle.pk]))
        self.assertContains(response, "Hapus Kendaraan")
        self.assertContains(response, "B 9021 XY")
        self.assertContains(response, f'action="{reverse("fleet:vehicle_delete", args=[self.vehicle.pk])}"')
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_delete_removes_photo_files(self):
        foto = VehiclePhoto.objects.create(vehicle=self.vehicle, image=_png_upload())
        storage, name = foto.image.storage, foto.image.name
        self.assertTrue(storage.exists(name))
        self.client.post(reverse("fleet:vehicle_delete", args=[self.vehicle.pk]))
        self.assertFalse(storage.exists(name))


class VehicleQrCodeTests(TestCase):
    def test_qr_text_lists_vehicle_identity(self):
        vehicle = Vehicle(nopol="B 9021 XY", merek="Hino Dutro", no_chasis="MHFXX123", no_mesin="W04DTR456")
        self.assertEqual(
            vehicle.qr_text(),
            "No. Registrasi: B 9021 XY\nMerk/Type: Hino Dutro\nNo. Chasis: MHFXX123\nNo. Mesin: W04DTR456",
        )

    def test_qr_png_has_logo_in_centre(self):
        from .qr import qr_png_with_logo
        image = Image.open(io.BytesIO(qr_png_with_logo("No. Registrasi: B 9021 XY")))
        self.assertEqual(image.format, "PNG")
        centre = image.getpixel((image.width // 2, image.height // 2))
        corner = image.getpixel((5, 5))
        self.assertEqual(corner, (255, 255, 255))
        self.assertNotIn(centre, [(0, 0, 0), (255, 255, 255)])

    def test_qr_view_requires_login_and_serves_png(self):
        vehicle = Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro", odometer_km=1)
        url = reverse("fleet:vehicle_qr", args=[vehicle.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Cache-Control"], "private, no-cache")
        self.assertNotIn("Content-Disposition", response)
        response = self.client.get(url + "?unduh=1")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="qr-b-9021-xy.png"')

    def test_list_shows_qr_code_and_foto_columns(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro", odometer_km=45000)
        self.client.login(username="teknisi1", password="rahasia-123")
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertContains(response, "QR Code</th>")
        self.assertContains(response, "Foto Kendaraan</th>")
        vehicle = Vehicle.objects.get()
        # The list only shows an icon button; the QR image lives in the modal.
        self.assertContains(response, f'hx-get="{reverse("fleet:vehicle_qr_modal", args=[vehicle.pk])}"', count=2)
        self.assertNotContains(response, 'alt="QR Code B 9021 XY"')

        response = self.client.get(reverse("fleet:vehicle_qr_modal", args=[vehicle.pk]))
        self.assertContains(
            response, f'src="{reverse("fleet:vehicle_qr", args=[vehicle.pk])}?v={vehicle.qr_version()}"'
        )
        # Without download, the page loading bar treats the link as a
        # navigation and stays stuck because the page never unloads.
        self.assertContains(response, 'download="qr-b-9021-xy.png"')

    def test_qr_version_changes_when_no_mesin_changes(self):
        vehicle = Vehicle(nopol="B 9021 XY", merek="Hino Dutro")
        before = vehicle.qr_version()
        vehicle.no_mesin = "W04DTR456"
        self.assertNotEqual(before, vehicle.qr_version())
        self.assertIn("No. Mesin: W04DTR456", vehicle.qr_text())


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class VehicleFotoUploadTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.client.login(username="teknisi1", password="rahasia-123")

    def _create(self, photos):
        return self.client.post(reverse("fleet:vehicle_create"), {
            "nopol": "B 1234 AB",
            "merek": "Toyota Avanza",
            "odometer_km": 1000,
            "foto": photos,
        })

    def test_create_with_four_fotos_saves_them_and_lists_them(self):
        response = self._create(_photos(4))
        self.assertRedirects(response, reverse("fleet:vehicle_list"))
        vehicle = Vehicle.objects.get()
        self.assertEqual(vehicle.fotos.count(), 4)
        self.assertTrue(all(f.image.name.startswith("kendaraan/") for f in vehicle.fotos.all()))
        response = self.client.get(reverse("fleet:vehicle_list"))
        self.assertContains(response, f'hx-get="{reverse("fleet:vehicle_photos", args=[vehicle.pk])}"', count=2)
        self.assertContains(response, "Lihat (4)")
        response = self.client.get(reverse("fleet:vehicle_photos", args=[vehicle.pk]))
        self.assertContains(response, "Foto Kendaraan B 1234 AB")
        for foto in vehicle.fotos.all():
            self.assertContains(response, f'src="{foto.image.url}"')

    def test_uploaded_fotos_are_compressed_to_jpeg(self):
        buffer = io.BytesIO()
        Image.effect_noise((4000, 3000), 80).convert("RGB").save(buffer, format="PNG")
        big = buffer.getvalue()
        uploads = [SimpleUploadedFile(f"besar-{i}.png", big, content_type="image/png") for i in range(4)]
        self.assertRedirects(self._create(uploads), reverse("fleet:vehicle_list"))
        foto = Vehicle.objects.get().fotos.first()
        self.assertTrue(foto.image.name.endswith(".jpg"))
        self.assertLess(foto.image.size, len(big))
        with Image.open(foto.image) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(max(img.size), 1600)

    def test_photos_modal_requires_login(self):
        self._create(_photos(4))
        vehicle = Vehicle.objects.get()
        self.client.logout()
        response = self.client.get(reverse("fleet:vehicle_photos", args=[vehicle.pk]))
        self.assertEqual(response.status_code, 302)

    def test_create_with_fewer_than_four_fotos_is_rejected(self):
        response = self._create(_photos(3))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vehicle.objects.count(), 0)
        self.assertContains(response, "Unggah minimal 4 foto kendaraan (baru 3).")

    def test_create_without_fotos_is_rejected(self):
        response = self._create([])
        self.assertEqual(Vehicle.objects.count(), 0)
        self.assertContains(response, "Unggah minimal 4 foto kendaraan (baru 0).")

    def test_edit_with_new_fotos_replaces_all_old_ones(self):
        self._create(_photos(4))
        vehicle = Vehicle.objects.get()
        old_ids = set(vehicle.fotos.values_list("id", flat=True))
        response = self.client.post(reverse("fleet:vehicle_update", args=[vehicle.pk]), {
            "nopol": "B 1234 AB", "merek": "Toyota Avanza", "odometer_km": 1000, "foto": _photos(5),
        })
        self.assertRedirects(response, reverse("fleet:vehicle_list"))
        self.assertEqual(vehicle.fotos.count(), 5)
        self.assertFalse(old_ids & set(vehicle.fotos.values_list("id", flat=True)))

    def test_edit_with_too_few_new_fotos_keeps_old_ones(self):
        self._create(_photos(4))
        vehicle = Vehicle.objects.get()
        response = self.client.post(reverse("fleet:vehicle_update", args=[vehicle.pk]), {
            "nopol": "B 1234 AB", "merek": "Toyota Avanza", "odometer_km": 1000, "foto": _photos(2),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(vehicle.fotos.count(), 4)

    def test_form_posts_as_multipart_for_htmx(self):
        response = self.client.get(reverse("fleet:vehicle_create"), HTTP_HX_REQUEST="true")
        self.assertContains(response, 'hx-encoding="multipart/form-data"')


class AdminRegistrationTests(TestCase):
    def test_every_project_model_is_registered_in_admin(self):
        from django.apps import apps
        from django.contrib import admin

        for app_label in ("accounts", "fleet"):
            for model in apps.get_app_config(app_label).get_models():
                self.assertTrue(admin.site.is_registered(model), f"{model.__name__} not in admin")

    def test_admin_changelists_render(self):
        User.objects.create_superuser(username="admin", password="rahasia-123")
        self.client.login(username="admin", password="rahasia-123")
        Vehicle.objects.create(nopol="B 9021 XY", merek="Hino Dutro", odometer_km=1)
        for name in ("fleet_vehicle", "fleet_vehiclephoto", "accounts_laporan", "accounts_revokedtoken"):
            response = self.client.get(reverse(f"admin:{name}_changelist"))
            self.assertEqual(response.status_code, 200, name)
