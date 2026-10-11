"""Form Perbaikan saves itself every 10 seconds into a DraftPerbaikan."""
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import Anggota, DraftPerbaikan
from fleet.models import Vehicle


class DraftPerbaikanTests(TestCase):
    def setUp(self):
        ketua = User.objects.create_user(username="ketua1", password="x")
        ketua.groups.add(Group.objects.get(name="Ketua Tim"))
        self.teknisi = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.teknisi.groups.add(Group.objects.get(name="Tim Perbaikan"))
        Anggota.add_root(user=ketua).add_child(user=self.teknisi)
        self.vehicle = Vehicle.objects.create(nopol="R 5 DP", merek="Maung", group_kendaraan="rantis")
        self.url = reverse("accounts:perbaikan_draft", args=[self.vehicle.uuid])
        self.client.login(username="teknisi1", password="rahasia-123")

    def _simpan(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def test_saves_and_returns_the_draft_per_vehicle_and_user(self):
        self.assertEqual(self.client.get(self.url).json(), {})
        data = {"perbaikan_7_aktif": "1", "perbaikan_7_kondisi": "RR", "perbaikan_7_keterangan": "ganti baut"}
        self.assertEqual(self._simpan(data).json(), {"ok": True})
        self._simpan({**data, "perbaikan_7_keterangan": "las ulang"})  # the same row, replaced
        draft = DraftPerbaikan.objects.get()
        self.assertEqual((draft.vehicle, draft.teknisi, draft.data["perbaikan_7_keterangan"]), (self.vehicle, self.teknisi, "las ulang"))
        self.assertEqual(self.client.get(self.url).json()["perbaikan_7_kondisi"], "RR")
        self.assertEqual(self.client.post(self.url, "bukan json", content_type="application/json").status_code, 400)

    def test_the_page_saves_itself_every_ten_seconds(self):
        halaman = self.client.get(reverse("accounts:perbaikan"))
        self.assertContains(halaman, "setInterval(() => this.saveDraft(), 10000)")
        self.assertContains(halaman, "/perbaikan/draft/")

    def test_a_superuser_is_not_saved(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertEqual(self._simpan({"a": "b"}).json(), {"ok": True})
        self.assertFalse(DraftPerbaikan.objects.exists())

    def test_simpan_sent_twice_records_the_repair_once(self):
        from accounts.models import Laporan, PemeriksaanRantis, PemeriksaanRantisItem, PerbaikanRantis, Satuan
        bio = Laporan.objects.create(
            akun=self.teknisi, nip="1", nama="BUDI", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="YON UJI"),
        )
        hasil = PemeriksaanRantis.objects.create(
            pemeriksa=bio, vehicle=self.vehicle, km_berfungsi="ya", jam_mesin_berfungsi="ya", buku_pemeliharaan="ada",
            kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        item = PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=1, nama_alat="Rem", kondisi="RR")
        data = {
            "vehicle": str(self.vehicle.uuid), f"perbaikan_{item.pk}_aktif": "1",
            f"perbaikan_{item.pk}_kondisi": "RR", f"perbaikan_{item.pk}_keterangan": "tunggu suku cadang",
        }
        for _ in range(2):  # a second click while the first is still uploading
            self.assertEqual(self.client.post(reverse("accounts:perbaikan"), data).status_code, 302)
        self.assertEqual(PerbaikanRantis.objects.count(), 1)
        # A different result for the same part is a new repair.
        self.client.post(reverse("accounts:perbaikan"), {**data, f"perbaikan_{item.pk}_kondisi": "B"})
        self.assertEqual(PerbaikanRantis.objects.count(), 2)
