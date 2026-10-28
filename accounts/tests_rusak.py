"""Form Rusak/Tidak Layak Pakai: a Tim member declares a vehicle beyond use."""
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import dashboard, roles
from accounts.models import Anggota, KendaraanRusak, Laporan, PemeriksaanRantis, PemeriksaanRantisItem, Satuan
from fleet.models import Vehicle

TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x00\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FormRusakTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:rusak")
        ketua = User.objects.create_user(username="ketua1", password="x")
        ketua.groups.add(Group.objects.get(name="Ketua Tim"))
        node = Anggota.add_root(user=ketua)
        self.teknisi = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.teknisi.groups.add(Group.objects.get(name="Tim Pemeriksaan Rusak/Tidak Layak"))
        node.add_child(user=self.teknisi)
        self.bio = Laporan.objects.create(
            akun=self.teknisi, nip="1", nama="BUDI", pangkat="P", jabatan="J", satuan=Satuan.objects.create(nama="YON UJI"),
            foto="laporan/x.jpg",
        )
        self.vehicle = Vehicle.objects.create(nopol="R 7 RS", merek="Maung", group_kendaraan="rantis")
        self.client.login(username="teknisi1", password="rahasia-123")

    def _nyatakan(self, **data):
        return self.client.post(self.url, {"vehicle": str(self.vehicle.uuid), "alasan": "Rangka patah", **data})

    def test_menu_is_for_tim_pemeriksaan_rusak_tidak_layak(self):
        self.assertIn("rusak", roles.allowed_menus(self.teknisi))
        halaman = self.client.get(self.url)
        self.assertContains(halaman, "Form Rusak/Tidak Layak Pakai")
        self.assertContains(halaman, f'href="{self.url}"')
        self.assertEqual(roles.keanggotaan_kode(self.teknisi), "tim_tidak_layak")
        self.assertIn("tim_tidak_layak", roles.TIM)
        self.assertEqual(roles.MENU_PER_KEANGGOTAAN["tim_tidak_layak"], ["info_profile", "rusak", "history", "status"])
        # The other Tim roles don't have the form.
        for i, group in enumerate(("Tim Penambahan Data", "Tim Pemeriksaan", "Tim Perbaikan")):
            lain = User.objects.create_user(username=f"lain{i}", password="rahasia-123")
            lain.groups.add(Group.objects.get(name=group))
            Anggota.objects.get(user__username="ketua1").add_child(user=lain)
            self.assertNotIn("rusak", roles.allowed_menus(lain), group)
            self.client.login(username=f"lain{i}", password="rahasia-123")
            self.assertEqual(self.client.get(self.url).status_code, 302, group)
        # A Ketua Tim offers the new team when adding a member.
        self.client.login(username="ketua1", password="x")
        node = Anggota.objects.get(user__username="ketua1")
        tambah = self.client.get(reverse("accounts:anggota_tim_tambah", args=[node.uuid]))
        self.assertContains(tambah, '<option value="tim_tidak_layak">Tim Pemeriksaan Rusak/Tidak Layak</option>', html=True)
        ubah = self.client.get(reverse("accounts:anggota_tim_ubah", args=[self.teknisi.publik.uuid]))
        self.assertContains(ubah, "Tim Pemeriksaan Rusak/Tidak Layak")

    def test_form_for_the_scanned_vehicle(self):
        form = self.client.get(reverse("accounts:rusak_kendaraan"), {"nopol": "R 7 RS"})
        for text in ("R 7 RS", "Maung", 'name="alasan"', 'name="rusak_foto"', f'value="{self.vehicle.uuid}"'):
            self.assertContains(form, text)
        self.assertContains(self.client.get(reverse("accounts:rusak_kendaraan"), {"nopol": "ZZZ"}), "Kendaraan tidak ditemukan")

    def test_declaring_makes_the_vehicle_rusak_berat(self):
        gagal = self._nyatakan(alasan="  ")
        self.assertContains(gagal, "Isi alasan / keterangan kerusakan.")
        self.assertFalse(KendaraanRusak.objects.exists())
        response = self._nyatakan(rusak_foto=SimpleUploadedFile("foto.gif", TINY_GIF, content_type="image/gif"))
        self.assertEqual(response.status_code, 302)
        rusak = KendaraanRusak.objects.get()
        self.assertEqual((rusak.vehicle, rusak.pelapor, rusak.alasan, len(rusak.daftar_foto)), (self.vehicle, self.bio, "Rangka patah", 1))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.DALAM_PERBAIKAN)
        # Counted Rusak Berat on the dashboard (no matra anywhere: the first one's).
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        tab = self.client.get(reverse("accounts:dashboard"), {"matra": "darat"})
        self.assertEqual(tab.context["fleet_summary_kendaraan"]["in_repair"], 1)
        # The form shows what was declared before.
        self.assertContains(self.client.get(reverse("accounts:rusak_kendaraan"), {"nopol": "R 7 RS"}), "Rangka patah")

    def test_a_later_inspection_decides_again(self):
        self._nyatakan()
        hasil = PemeriksaanRantis.objects.create(
            pemeriksa=self.bio, vehicle=self.vehicle, km_berfungsi="ya", jam_mesin_berfungsi="ya",
            buku_pemeliharaan="ada", kondisi_ranmor="jalan", macam_pemeriksaan="tehnis", kesimpulan="siap_pakai",
        )
        PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=1, nama_alat="A", kondisi="B")
        from accounts import golongan
        self.assertEqual(golongan.perbarui_status(self.vehicle), Vehicle.Status.SIAP_PAKAI)
        # Declared again after that inspection: Rusak Berat again.
        self._nyatakan(alasan="Terbakar")
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, Vehicle.Status.DALAM_PERBAIKAN)

    def test_needs_biodata_and_a_vehicle(self):
        self.bio.delete()
        self.assertContains(self._nyatakan(), "Isi biodata di Info Profil terlebih dahulu.")
        self.assertContains(self.client.post(self.url, {"alasan": "x"}), "Scan QR Code kendaraan terlebih dahulu.")
        self.assertFalse(KendaraanRusak.objects.exists())


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanRusakTests(TestCase):
    def setUp(self):
        self.bio = Laporan.objects.create(nip="1", nama="BUDI", pangkat="KAPTEN", jabatan="J", satuan=Satuan.objects.create(nama="YON UJI"))
        self.rusak = Vehicle.objects.create(nopol="R 7 RS", merek="Maung", group_kendaraan="rantis")
        Vehicle.objects.create(nopol="R 8 OK", merek="Maung", group_kendaraan="rantis")
        KendaraanRusak.objects.create(vehicle=self.rusak, pelapor=self.bio, alasan="Rangka patah")
        from accounts import golongan
        golongan.perbarui_status(self.rusak)
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:laporan_rusak")

    def test_report_lists_declared_vehicles_and_opens_their_detail(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Laporan Rusak/Tidak Layak Pakai")
        self.assertContains(response, f'href="{self.url}"')
        # Tanggal (the newest declaration) first, then No. Registrasi.
        self.assertEqual(response.context["header"][:2], ["Tanggal", "No. Registrasi"])
        self.assertEqual([baris[1] for baris, _ in response.context["halaman"]], ["R 7 RS"])
        self.assertRegex(response.context["halaman"][0][0][0], r"^\d{2}-\d{2}-\d{4} \d{2}:\d{2}$")
        self.assertEqual(response.context["halaman"][0][0][-1], "YON UJI")
        self.assertEqual(self.client.get(self.url, {"q": "zzz"}).context["total"], 0)
        detail = self.client.get(reverse("accounts:laporan_rusak_detail", args=[self.rusak.uuid]))
        for text in ("Rangka patah", "BUDI", "KAPTEN", "YON UJI", "Personil yang Menyatakan"):
            self.assertContains(detail, text)

    def test_tabs_sparepart_kendaraan_and_non_kendaraan(self):
        from accounts.models import PemeriksaanRantis, PemeriksaanRantisItem
        response = self.client.get(self.url)
        self.assertEqual(response.context["tab_aktif"], "kendaraan")
        for kode, label in (("sparepart", "Sparepart"), ("kendaraan", "Kendaraan"), ("non_kendaraan", "Non Kendaraan")):
            self.assertContains(response, f'<a href="?tab={kode}"')
            self.assertContains(response, label)
        hasil = PemeriksaanRantis.objects.create(
            pemeriksa=self.bio, vehicle=self.rusak, km_berfungsi="ya", jam_mesin_berfungsi="ya", buku_pemeliharaan="ada",
            kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=3, nama_alat="Gardan", kondisi="RB", keterangan="pecah")
        PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=4, nama_alat="Lampu", kondisi="RR")
        sparepart = self.client.get(self.url, {"tab": "sparepart"})
        self.assertEqual([baris[:2] for baris, _ in sparepart.context["halaman"]], [("Gardan", "R 7 RS")])
        self.assertEqual(self.client.get(self.url, {"tab": "sparepart", "q": "lampu"}).context["total"], 0)
        self.assertIn(".xlsx", self.client.get(self.url, {"tab": "sparepart", "unduh": "excel"})["Content-Disposition"])
        self.assertEqual(self.client.get(self.url, {"tab": "non_kendaraan"}).context["total"], 0)

    def test_ketua_tim_edits_and_deletes_a_pimpinan_only_reads(self):
        pimpinan = User.objects.create_user(username="pimpinan1", password="rahasia-123")
        pimpinan.groups.add(Group.objects.get_or_create(name="Pimpinan")[0])
        hapus = reverse("accounts:laporan_hapus", args=["rusak", self.rusak.uuid])
        edit = reverse("fleet:vehicle_update", args=[self.rusak.uuid])
        self.client.login(username="pimpinan1", password="rahasia-123")
        laporan = self.client.get(self.url)
        self.assertEqual(laporan.status_code, 200)
        self.assertNotContains(laporan, hapus)
        self.assertEqual(self.client.get(hapus).status_code, 403)
        self.assertEqual(self.client.get(edit).status_code, 403)

        ketua = User.objects.create_user(username="ketua1", password="rahasia-123")
        ketua.groups.add(Group.objects.get(name="Ketua Tim"))
        Anggota.add_root(user=ketua)
        self.assertIn("laporan_rusak", roles.allowed_menus(ketua))
        self.client.login(username="ketua1", password="rahasia-123")
        laporan = self.client.get(self.url)
        self.assertContains(laporan, hapus)
        self.assertContains(laporan, f"{edit}?next=")
        # Edit: the vehicle's data (its photos kept), saved back to this report.
        from fleet.models import VehiclePhoto
        for _ in range(4):
            VehiclePhoto.objects.create(vehicle=self.rusak, image="x.jpg")
        form = self.client.get(edit, {"next": self.url}, HTTP_HX_REQUEST="true")
        self.assertContains(form, "Edit Kendaraan")
        self.assertContains(form, f"?next={self.url}")
        simpan = self.client.post(
            f"{edit}?next={self.url}",
            {"nopol": "R 7 RS", "merek": "Maung Baru", "kepemilikan": self.rusak.kepemilikan},
            HTTP_HX_REQUEST="true",
        )
        self.rusak.refresh_from_db()
        self.assertEqual((self.rusak.merek, simpan["HX-Redirect"]), ("MAUNG BARU", self.url))
        # Hapus: confirmed with the code shown.
        self.assertContains(self.client.get(hapus), "1 pernyataan rusak/tidak layak pakai")
        self.client.post(hapus, {"captcha": self.client.session[f"hapus_laporan_rusak_{self.rusak.pk}"]})
        self.assertFalse(KendaraanRusak.objects.exists())
        self.rusak.refresh_from_db()
        # The vehicle stays, back on what its inspections say (none: Siap).
        self.assertEqual(self.rusak.status, Vehicle.Status.SIAP_PAKAI)


class RekapKerusakanTests(TestCase):
    """Rekap Kerusakan: the parts damaged now, with their condition and vehicle group."""

    def setUp(self):
        from accounts.models import (
            PemeriksaanGolonganB, PemeriksaanGolonganBItem, PemeriksaanRantis, PemeriksaanRantisItem, PerbaikanRantis,
        )
        satuan = Satuan.objects.create(nama="YON REKAP")
        self.bio = Laporan.objects.create(nip="9", nama="SARI", pangkat="P", jabatan="J", satuan=satuan)
        rantis = Vehicle.objects.create(nopol="R 1 RK", merek="Maung", group_kendaraan="rantis", penambah=self.bio)
        gol_b = Vehicle.objects.create(nopol="B 2 RK", merek="Isuzu", group_kendaraan="B")
        hasil = PemeriksaanRantis.objects.create(
            pemeriksa=self.bio, vehicle=rantis, km_berfungsi="ya", jam_mesin_berfungsi="ya", buku_pemeliharaan="ada",
            kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        item = {
            nama: PemeriksaanRantisItem.objects.create(pemeriksaan=hasil, nomor=n, nama_alat=nama, kondisi=kondisi, keterangan=f"ket {nama}")
            for n, (nama, kondisi) in enumerate(
                (("Gardan", "RB"), ("Lampu", "RR"), ("Rem", "RR"), ("Kaca", "B"), ("Dongkrak", "TA")), start=1,
            )
        }
        PerbaikanRantis.objects.create(teknisi=self.bio, item=item["Rem"], kondisi="B")  # repaired: listed as found -> now
        periksa_b = PemeriksaanGolonganB.objects.create(
            pemeriksa=self.bio, vehicle=gol_b, pembagian_kelas="A", eselon_reparasi="1", macam_pemeriksaan="tehnis", buku_jalan="ada",
        )
        PemeriksaanGolonganBItem.objects.create(pemeriksaan=periksa_b, nomor=7, nama_alat="Kopling", kondisi="RR", keterangan="aus")
        self.satuan = satuan
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:rekap_kerusakan")

    def _komponen(self, **query):
        response = self.client.get(self.url, query)
        return {baris[5] for baris, _ in response.context["halaman"]}

    def test_lists_damaged_parts_with_condition_and_group(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Rekap Kerusakan")
        self.assertContains(response, f'href="{self.url}"')  # the sidebar entry
        self.assertNotContains(response, "Form No")
        for text in ("Jenis Kendaraan", "Kondisi", "Rusak Berat", "Rusak Ringan", "RANTIS", "Golongan B", 'name="kondisi"', 'name="dari"'):
            self.assertContains(response, text)
        # Ten rows a page here (the other tables page at 15).
        self.assertEqual(response.context["halaman"].paginator.per_page, 10)
        self.assertEqual(self.client.get(reverse("accounts:laporan_rusak")).context["halaman"].paginator.per_page, 15)
        # What the last inspection found damaged; Kaca (Baik) and Dongkrak (Tidak Ada) are not damage.
        self.assertEqual(self._komponen(), {"Gardan", "Lampu", "Rem", "Kopling"})
        baris = {b[5]: b for b, _ in response.context["halaman"]}
        self.assertEqual(baris["Gardan"][1:5], ("R 1 RK", "Maung", "RANTIS", "YON REKAP"))
        # Not repaired yet: the one condition. Repaired: what was found, an arrow, what it is now.
        import re

        def kondisi(nama):
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(baris[nama][6]))).strip()

        self.assertEqual((kondisi("Gardan"), kondisi("Lampu")), ("Rusak Berat", "Rusak Ringan"))
        self.assertEqual(kondisi("Rem"), "Rusak Ringan → Baik")
        self.assertEqual((baris["Rem"][7], baris["Gardan"][7]), ("Perbaikan", "Pemeriksaan"))
        # A repair that left the part damaged shows both conditions too.
        from accounts.models import PemeriksaanRantisItem, PerbaikanRantis
        PerbaikanRantis.objects.create(teknisi=self.bio, item=PemeriksaanRantisItem.objects.get(nama_alat="Lampu"), kondisi="RB")
        baris = {b[5]: b for b, _ in self.client.get(self.url).context["halaman"]}
        self.assertEqual(kondisi("Lampu"), "Rusak Ringan → Rusak Berat")

    def test_filters(self):
        from django.utils import timezone
        hari_ini = timezone.localdate().isoformat()
        # Kondisi: what the part is now (after the arrow, for a repaired one). Rem: Rusak Ringan -> Baik.
        self.assertEqual(self._komponen(kondisi="RB"), {"Gardan"})
        self.assertEqual(self._komponen(kondisi="RR"), {"Lampu", "Kopling"})
        self.assertEqual(self._komponen(kondisi="B"), {"Rem"})
        self.assertContains(self.client.get(self.url, {"kondisi": "B"}), '<option value="B" selected>Baik</option>')
        self.assertEqual(self._komponen(golongan="B"), {"Kopling"})
        self.assertEqual(self._komponen(golongan="rantis", kondisi="RR"), {"Lampu"})
        self.assertEqual(self._komponen(satuan=str(self.satuan.uuid)), {"Gardan", "Lampu", "Rem"})
        self.assertEqual(self._komponen(q="r 1 rk"), {"Gardan", "Lampu", "Rem"})
        self.assertEqual(self._komponen(q="kopling"), {"Kopling"})
        self.assertEqual(len(self._komponen(dari=hari_ini, sampai=hari_ini)), 4)
        self.assertEqual(self._komponen(sampai="2000-01-01"), set())
        self.assertEqual(len(self._komponen(kondisi="zz", golongan="zz")), 4)

    def test_excel_and_access(self):
        from io import BytesIO

        from openpyxl import load_workbook
        from accounts import roles
        response = self.client.get(self.url, {"unduh": "excel", "kondisi": "RB"})
        rows = list(load_workbook(BytesIO(response.content)).active.values)
        self.assertEqual(rows[3][:8], ("No", "Tanggal", "No. Registrasi", "Merk/Type", "Jenis Kendaraan", "Satuan", "Sparepart / Komponen", "Kondisi"))
        self.assertEqual((len(rows) - 4, rows[4][6:8]), (1, ("Gardan", "Rusak Berat")))
        # The PDF: a chart per unit over the detail table, following the filter.
        from unittest import mock
        from accounts import laporan_pdf
        self.assertContains(self.client.get(self.url, {"kondisi": "RR"}), "kondisi=RR&amp;unduh=pdf")
        with mock.patch.object(laporan_pdf, "buat_pdf_rekap_kerusakan", wraps=laporan_pdf.buat_pdf_rekap_kerusakan) as buat:
            pdf = self.client.get(self.url, {"unduh": "pdf"})
            terfilter = self.client.get(self.url, {"unduh": "pdf", "kondisi": "RB"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF") and terfilter.content.startswith(b"%PDF"))
        _, per_satuan, kepala, lebar, baris = buat.call_args_list[0].args
        self.assertEqual(sorted(per_satuan), [("-", 0, 1), ("YON REKAP", 1, 1)])  # (unit, Rusak Berat, Rusak Ringan)
        # The pies count what is still damaged; the part repaired to Baik is a number of its own.
        self.assertEqual((len(baris), len(lebar), sum(lebar)), (4, len(kepala) + 1, 267))
        self.assertEqual(buat.call_args_list[0].kwargs, {"sudah_baik": 1})
        self.assertIn("Rusak Ringan → Baik", [b[6] for b in baris])
        keterangan, per_satuan, _, _, baris = buat.call_args_list[1].args
        self.assertEqual((per_satuan, len(baris)), ([("YON REKAP", 1, 0)], 1))
        self.assertIn("Rusak Berat", keterangan)
        # More units than the chart draws: the rest are named under it, and an empty report still builds.
        banyak = [(f"SATUAN {i}", i, 1) for i in range(1, 25)]
        self.assertTrue(laporan_pdf.buat_pdf_rekap_kerusakan("uji", banyak, kepala, lebar, []).startswith(b"%PDF"))
        self.assertTrue(laporan_pdf.buat_pdf_rekap_kerusakan("uji", [], kepala, lebar, []).startswith(b"%PDF"))
        # Admin and Pimpinan have the menu; a Tim member does not.
        for grup, punya in (("Admin", True), ("Pimpinan", True), ("Tim Perbaikan", False), ("Ketua Tim", False)):
            user = User.objects.create_user(username=f"u_{grup}".replace(" ", "_"), password="rahasia-123")
            user.groups.add(Group.objects.get(name=grup))
            self.assertEqual("rekap_kerusakan" in roles.allowed_menus(user), punya, grup)
        self.client.login(username="u_Tim_Perbaikan", password="rahasia-123")
        self.assertEqual(self.client.get(self.url).status_code, 302)
