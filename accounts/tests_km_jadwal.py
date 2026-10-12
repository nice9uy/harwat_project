"""Pengaturan > KM: the interval of each part marked * on the inspection form."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import KmJadwal


class KmJadwalTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:pengaturan")

    def test_tab_lists_the_marked_parts(self):
        response = self.client.get(self.url)
        self.assertContains(response, "tab = 'km'")
        for nama in ("KM Kendaraan", "Golongan B", "Km / Mil", "Kendaraan Diesel", "Jeep Diesel", "RANTIS", "RANSUS", "Oli Mesin", "Oli Persneling / Transmisi", "Oli Gardan"):
            self.assertContains(response, nama)
        self.assertContains(response, "Belum diatur", count=18)
        self.assertEqual(KmJadwal.objects.count(), 9)
        # A row that went missing is made again; ?tab=km opens the tab.
        KmJadwal.objects.filter(komponen="Oli Gardan").delete()
        self.assertContains(self.client.get(self.url, {"tab": "km"}), "tab: 'km'")
        self.assertEqual(KmJadwal.objects.count(), 9)

    def test_edit_interval(self):
        self.client.get(self.url)
        oli = KmJadwal.objects.get(komponen="Oli Mesin")
        edit = reverse("accounts:km_jadwal_edit", args=[oli.uuid])
        self.assertContains(self.client.get(edit), "Dicek setiap (km)")
        response = self.client.post(edit, {"interval_km": "5000"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response["HX-Redirect"], f"{self.url}?tab=km")
        oli.refresh_from_db()
        self.assertEqual(oli.interval_km, 5000)
        self.assertContains(self.client.get(self.url), "Setiap 5000 km")
        # Waktu Servis: a column of its own, in months.
        self.assertContains(self.client.get(self.url), ">Waktu Servis</th>")
        self.client.post(edit, {"interval_km": "5000", "interval_bulan": "6"})
        oli.refresh_from_db()
        self.assertEqual((oli.interval_km, oli.interval_bulan), (5000, 6))
        self.assertContains(self.client.get(self.url), "Setiap 6 bulan")
        self.assertEqual(self.client.post(edit, {"interval_km": "-1"}).status_code, 200)
        self.client.post(edit, {"interval_km": ""})
        oli.refresh_from_db()
        self.assertIsNone(oli.interval_km)
