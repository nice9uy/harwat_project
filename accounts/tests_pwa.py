"""The app on the phone's home screen and Hapus Cache: for a Ketua Tim and the
Tim members only; the manifest and the service worker for everyone."""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts import roles


def _user(username, grup=None):
    user = User.objects.create_user(username=username, password="rahasia-123")
    if grup:
        user.groups.add(Group.objects.get_or_create(name=grup)[0])
    return user


class MenuLapanganTests(TestCase):
    def test_only_ketua_tim_and_tim_members_get_the_menus(self):
        for grup in ("Ketua Tim", "Tim Pemeriksaan", "Tim Penambahan Data", "Tim Perbaikan", "Tim Pemeriksaan Rusak/Tidak Layak"):
            menus = roles.allowed_menus(_user(grup.replace(" ", "_").lower(), grup))
            self.assertTrue({"shortcut", "hapus_cache"} <= menus, grup)
        for user in (_user("admin1", "Admin"), _user("bos", "Pimpinan"), _user("pimtim", "Pimpinan Ketua Tim"),
                     User.objects.create_superuser(username="root", password="x")):
            self.assertFalse({"shortcut", "hapus_cache"} & roles.allowed_menus(user), user.username)

    def test_pages_and_sidebar(self):
        _user("tim1", "Tim Pemeriksaan")
        self.client.login(username="tim1", password="rahasia-123")
        self.assertContains(self.client.get(reverse("accounts:shortcut")), "Pasang Harwat di layar utama")
        halaman = self.client.get(reverse("accounts:hapus_cache"))
        self.assertContains(halaman, "Hapus cache aplikasi")
        self.assertContains(halaman, f'href="{reverse("accounts:shortcut")}"')
        self.assertContains(halaman, 'rel="manifest"')
        # An admin is sent away from them.
        _user("admin1", "Admin")
        self.client.login(username="admin1", password="rahasia-123")
        self.assertEqual(self.client.get(reverse("accounts:shortcut")).status_code, 302)

    def test_hapus_cache_server_side(self):
        _user("tim1", "Tim Pemeriksaan")
        self.client.login(username="tim1", password="rahasia-123")
        url = reverse("accounts:hapus_cache_server")
        self.assertEqual(self.client.get(url).status_code, 405)
        respon = self.client.post(url)
        self.assertEqual(respon.status_code, 204)
        self.assertEqual(respon["Clear-Site-Data"], '"cache"')


class ManifestTests(TestCase):
    def test_manifest_and_service_worker_for_everyone(self):
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest["Content-Type"], "application/manifest+json")
        data = json.loads(manifest.content)
        self.assertEqual((data["short_name"], data["display"], data["start_url"]), ("Harwat", "standalone", "/"))
        self.assertTrue(any(i["sizes"] == "512x512" and i["purpose"] == "maskable" for i in data["icons"]))
        sw = self.client.get("/sw.js")
        self.assertEqual(sw["Content-Type"], "application/javascript")
        self.assertEqual(sw["Service-Worker-Allowed"], "/")
