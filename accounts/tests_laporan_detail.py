"""Laporan Pemeriksaan rows open a modal with the vehicle's inspections and inspectors."""
import tempfile

from django.contrib.auth.models import Group, User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Laporan, PemeriksaanGolonganB, PemeriksaanGolonganBItem, Satuan
from fleet.models import Vehicle


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanPemeriksaanDetailTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        self.vehicle = Vehicle.objects.create(nopol="B 1 X", merek="Hino", no_chasis="C1", no_mesin="M1")

    def _biodata(self, nip, nama):
        return Laporan.objects.create(
            nip=nip, nama=nama, pangkat="Kapten", jabatan="Teknisi", satuan=self.satuan, foto="x.gif",
        )

    def _pemeriksaan(self, pemeriksa, rusak=1):
        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, pembagian_kelas="1", eselon_reparasi="1",
            macam_pemeriksaan="tehnis", buku_jalan="ada", kesatuan=self.satuan,
        )
        for nomor in range(1, 6):
            PemeriksaanGolonganBItem.objects.create(
                pemeriksaan=hasil, nomor=nomor, nama_alat=f"Alat {nomor}", kondisi="RB" if nomor <= rusak else "B",
            )
        return hasil

    def _url(self):
        return reverse("accounts:laporan_pemeriksaan_detail", args=[self.vehicle.uuid])

    def test_report_rows_open_the_detail_modal(self):
        hasil = self._pemeriksaan(self._biodata("1", "Budi"))
        response = self.client.get(reverse("accounts:laporan_pemeriksaan"))
        self.assertContains(response, f'hx-get="{self._url()}"')
        self.assertEqual(hasil.vehicle.nopol, response.context["halaman"][0][0][0])
        self.assertContains(response, 'id="laporan-modal-body"')

    def test_tabs_list_inspections_and_personnel_once_per_person(self):
        budi, budi_lagi, ani = self._biodata("1", "Budi"), self._biodata("1", "Budi"), self._biodata("2", "Ani")
        pertama = self._pemeriksaan(budi, rusak=2)
        self._pemeriksaan(budi_lagi)
        self._pemeriksaan(ani)
        response = self.client.get(self._url(), {"pemeriksaan": pertama.uuid})
        self.assertContains(response, "Riwayat Pemeriksaan")
        self.assertContains(response, "Personil yang Memeriksa")
        self.assertEqual(len(response.context["riwayat"]), 3)
        self.assertEqual(response.context["dipilih"], pertama.uuid)
        self.assertContains(response, "Dipilih", count=1)
        personil = {p["biodata"].nip: p["jumlah"] for p in response.context["personil"]}
        self.assertEqual(personil, {"1": 2, "2": 1})
        baris = next(h for h in response.context["riwayat"] if h.pk == pertama.pk)
        self.assertEqual((baris.jumlah_baik, baris.jumlah_perlu), (3, 2))

    def test_query_count_does_not_grow(self):
        self._pemeriksaan(self._biodata("1", "Budi"))

        def hitung():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self._url())
            return len(ctx)
        sedikit = hitung()
        for i in range(4):
            self._pemeriksaan(self._biodata(str(10 + i), f"Orang {i}"))
        self.assertEqual(sedikit, hitung())

    def test_menu_access_follows_laporan_pemeriksaan(self):
        user = User.objects.create_user(username="tim", password="rahasia-123")
        user.groups.add(Group.objects.get(name="Tim Pemeriksaan"))
        self.client.login(username="tim", password="rahasia-123")
        response = self.client.get(self._url())
        self.assertNotEqual(response.status_code, 200)

    def test_pdf_export_of_one_inspection(self):
        from accounts.models import PerbaikanGolonganB

        pemeriksa = self._biodata("1", "Budi")
        hasil = self._pemeriksaan(pemeriksa, rusak=2)
        PerbaikanGolonganB.objects.create(teknisi=pemeriksa, item=hasil.items.get(nomor=1), kondisi="B")
        url = reverse("accounts:laporan_pemeriksaan_pdf", args=["B", hasil.uuid])
        modal = self.client.get(self._url())
        self.assertContains(modal, f'href="{url}"')
        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("inline", response["Content-Disposition"])
        self.assertIn("attachment", self.client.get(url, {"unduh": 1})["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=["x", hasil.uuid])).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=["diesel", hasil.uuid])).status_code, 404)

    def test_pdf_for_every_group(self):
        from accounts.models import PemeriksaanBermotor, PemeriksaanBermotorItem, PemeriksaanDiesel, PemeriksaanDieselItem

        pemeriksa = self._biodata("1", "Budi")
        bermotor = PemeriksaanBermotor.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, buku_harian="ada", macam_pemeriksaan="tehnis",
        )
        PemeriksaanBermotorItem.objects.create(pemeriksaan=bermotor, nomor=1, nama_alat="Mesin", kondisi="HP")
        diesel = PemeriksaanDiesel.objects.create(
            pemeriksa=pemeriksa, vehicle=self.vehicle, km_berfungsi="ya", jam_mesin_berfungsi="ya",
            buku_pemeliharaan="ada", kondisi_ranmor="jalan", macam_pemeriksaan="tehnis",
        )
        PemeriksaanDieselItem.objects.create(
            pemeriksaan=diesel, nomor=1, nama_alat="Radiator", satuan="bh", jumlah_riil=1, jumlah_nyata=1, kondisi="ADA",
        )
        for kode, hasil in (("bermotor", bermotor), ("diesel", diesel)):
            response = self.client.get(reverse("accounts:laporan_pemeriksaan_pdf", args=[kode, hasil.uuid]))
            self.assertEqual(response.status_code, 200, kode)
            self.assertTrue(response.content.startswith(b"%PDF"), kode)


TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
    b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LaporanPerbaikanDanPenambahanTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = Satuan.objects.create(nama="Yonif 202")
        self.vehicle = Vehicle.objects.create(nopol="B 1 X", merek="Hino", no_chasis="C1", no_mesin="M1")

    def _biodata(self, nip, nama):
        return Laporan.objects.create(
            nip=nip, nama=nama, pangkat="Kapten", jabatan="Teknisi", satuan=self.satuan, foto="x.gif",
        )

    def _perbaikan(self, teknisi, n=1):
        from accounts.models import PerbaikanGolonganB

        hasil = PemeriksaanGolonganB.objects.create(
            pemeriksa=self._biodata("9", "Pemeriksa"), vehicle=self.vehicle, pembagian_kelas="1",
            eselon_reparasi="1", macam_pemeriksaan="tehnis", buku_jalan="ada",
        )
        item = PemeriksaanGolonganBItem.objects.create(pemeriksaan=hasil, nomor=1, nama_alat="Motor", kondisi="RB")
        return [PerbaikanGolonganB.objects.create(teknisi=teknisi, item=item, kondisi="RR") for _ in range(n)]

    def test_perbaikan_rows_open_modal_with_repairs_and_technicians(self):
        budi = self._biodata("1", "Budi")
        pertama, kedua = self._perbaikan(budi, n=2)
        self._perbaikan(self._biodata("2", "Ani"))
        detail = reverse("accounts:laporan_perbaikan_detail", args=[self.vehicle.uuid])
        laporan = self.client.get(reverse("accounts:laporan_perbaikan"))
        self.assertContains(laporan, f'hx-get="{detail}"')
        self.assertEqual(len(laporan.context["halaman"].object_list), 1)  # one row per vehicle
        modal = self.client.get(detail, {"perbaikan": pertama.uuid})
        self.assertContains(modal, "Riwayat Perbaikan")
        self.assertContains(modal, "Personil yang Memperbaiki")
        self.assertEqual(len(modal.context["riwayat"]), 3)
        self.assertContains(modal, "Dipilih", count=1)
        self.assertEqual({p["biodata"].nip: p["jumlah"] for p in modal.context["personil"]}, {"1": 2, "2": 1})
        pdf = reverse("accounts:laporan_perbaikan_pdf", args=["B", pertama.uuid])
        self.assertContains(modal, f'href="{pdf}"')
        response = self.client.get(pdf)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_perbaikan_modal_query_count_does_not_grow(self):
        self._perbaikan(self._biodata("1", "Budi"))
        url = reverse("accounts:laporan_perbaikan_detail", args=[self.vehicle.uuid])

        def hitung():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url)
            return len(ctx)
        sedikit = hitung()
        for i in range(3):
            self._perbaikan(self._biodata(str(10 + i), f"Orang {i}"), n=2)
        self.assertEqual(sedikit, hitung())

    def test_form_tambah_saves_biodata_as_penambah(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fotos = [SimpleUploadedFile(f"m{i}.gif", TINY_GIF, content_type="image/gif") for i in range(4)]
        url = reverse("fleet:vehicle_create") + "?group=B&penambah=1&next=" + reverse("accounts:form_tambah")
        form = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertContains(form, 'hx-include="#form-tambah-biodata"')
        self.assertContains(form, "penambah=1")
        data = {
            "kepemilikan": "organik", "nopol": "B 7 X", "merek": "Isuzu", "foto": fotos,
            "penambah-nip": "123", "penambah-nama": "Sari", "penambah-pangkat": "Letda",
            "penambah-jabatan": "Staf", "penambah-satuan": self.satuan.pk,
            "penambah-foto": SimpleUploadedFile("p.gif", TINY_GIF, content_type="image/gif"),
        }
        response = self.client.post(url, data, HTTP_HX_REQUEST="true")
        self.assertEqual(response["HX-Redirect"], reverse("accounts:form_tambah"))
        vehicle = Vehicle.objects.get(nopol="B 7 X")
        self.assertEqual(vehicle.penambah.nama, "Sari")
        self.assertEqual(vehicle.penambah.akun, self.root)
        self.assertEqual(vehicle.ditambahkan_oleh, self.root)
        # Only one of the two "foto" fields is the biodata photo.
        self.assertEqual(vehicle.fotos.count(), 4)

    def test_form_tambah_without_complete_biodata_saves_nothing(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fotos = [SimpleUploadedFile(f"m{i}.gif", TINY_GIF, content_type="image/gif") for i in range(4)]
        url = reverse("fleet:vehicle_create") + "?group=B&penambah=1"
        response = self.client.post(url, {"kepemilikan": "organik", "nopol": "B 8 X", "merek": "Isuzu", "foto": fotos}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Biodata pemeriksa belum lengkap")
        self.assertFalse(Vehicle.objects.filter(nopol="B 8 X").exists())

    def test_penambahan_rows_open_modal_and_pdf(self):
        self.vehicle.penambah = self._biodata("5", "Sari")
        self.vehicle.ditambahkan_oleh = self.root
        self.vehicle.save()
        lama = Vehicle.objects.create(nopol="B 2 X", merek="Hino")
        detail = reverse("accounts:laporan_penambahan_detail", args=[self.vehicle.uuid])
        laporan = self.client.get(reverse("accounts:laporan_penambahan"))
        self.assertContains(laporan, f'hx-get="{detail}"')
        modal = self.client.get(detail)
        self.assertContains(modal, "Detail Kendaraan/Barang")
        self.assertContains(modal, "Personil yang Menambahkan")
        self.assertContains(modal, "Sari")
        self.assertContains(modal, reverse("accounts:laporan_penambahan_pdf", args=[self.vehicle.uuid]))
        self.assertContains(
            self.client.get(reverse("accounts:laporan_penambahan_detail", args=[lama.uuid])), "belum tercatat",
        )
        for v in (self.vehicle, lama):
            response = self.client.get(reverse("accounts:laporan_penambahan_pdf", args=[v.uuid]))
            self.assertTrue(response.content.startswith(b"%PDF"))

    def test_laporan_penambahan_role_can_see_the_qr_code(self):
        from accounts import roles

        self.assertIn("fleet:vehicle_qr", roles.MENU_VIEWS["laporan_penambahan"])


class QrLaporanTests(TestCase):
    def test_qr_text_has_vehicle_and_personnel(self):
        from accounts.laporan_pdf import _data_kendaraan_qr, _personil_qr, _teks_qr

        satuan = Satuan.objects.create(nama="Yonif 202")
        vehicle = Vehicle.objects.create(nopol="B 1 X", merek="Hino", no_chasis="C1")
        teknisi = Laporan.objects.create(
            nip="123", nama="Budi", pangkat="Kapten", jabatan="Teknisi", satuan=satuan, foto="x.gif",
        )
        teks = _teks_qr("Laporan Perbaikan Kendaraan", [
            _data_kendaraan_qr(vehicle, "Golongan B"), _personil_qr("Personil yang Memperbaiki", teknisi),
        ])
        for baris in ("Laporan Perbaikan Kendaraan", "No. Registrasi: B 1 X", "No. Mesin: -",
                      "[Personil yang Memperbaiki]", "NRP: 123", "Nama: Budi", "Satuan: Yonif 202"):
            self.assertIn(baris, teks.split("\n"))


class LaporanFilterSatuanTests(TestCase):
    """The three vehicle reports filter by the Satuan of whoever did the work."""

    def setUp(self):
        from accounts.models import PemeriksaanGolonganB, PemeriksaanGolonganBItem, PerbaikanGolonganB, Satuan
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.satuan = {}
        for nama in ("Alfa", "Bravo"):
            satuan = Satuan.objects.create(nama=nama)
            self.satuan[nama] = satuan
            orang = Laporan.objects.create(
                nip=nama, nama=f"Orang {nama}", pangkat="P", jabatan="J", satuan=satuan, foto="x.jpg",
            )
            vehicle = Vehicle.objects.create(nopol=f"B 1 {nama.upper()}", merek="Uji", group_kendaraan="B", penambah=orang)
            periksa = PemeriksaanGolonganB.objects.create(
                pemeriksa=orang, vehicle=vehicle, pembagian_kelas="1", eselon_reparasi="1",
                macam_pemeriksaan="tehnis", buku_jalan="ada",
            )
            item = PemeriksaanGolonganBItem.objects.create(pemeriksaan=periksa, nomor=1, nama_alat="Motor", kondisi="RR")
            PerbaikanGolonganB.objects.create(teknisi=orang, item=item, kondisi="B")

    def test_each_report_has_the_filter_and_narrows_by_it(self):
        for nama in ("accounts:laporan_pemeriksaan", "accounts:laporan_perbaikan", "accounts:laporan_penambahan"):
            semua = self.client.get(reverse(nama))
            self.assertContains(semua, 'name="satuan"')
            # Typed with suggestions (the units someone belongs to), not a dropdown.
            self.assertContains(semua, "x-data=\"autocomplete('opsi-satuan-filter'")
            self.assertIn("Alfa", [o["l"] for o in semua.context["satuan_opsi"]])
            self.assertContains(semua, "B 1 ALFA")
            self.assertContains(semua, "B 1 BRAVO")
            alfa = self.client.get(reverse(nama), {"satuan": self.satuan["Alfa"].uuid})
            self.assertContains(alfa, "B 1 ALFA", msg_prefix=nama)
            self.assertNotContains(alfa, "B 1 BRAVO", msg_prefix=nama)
            self.assertContains(alfa, f'name="satuan" :value="nilai" value="{self.satuan["Alfa"].uuid}"')
            # An unknown value is ignored.
            self.assertContains(self.client.get(reverse(nama), {"satuan": "zzz"}), "B 1 BRAVO")

    def test_laporan_tim_has_no_satuan_filter(self):
        self.assertNotContains(self.client.get(reverse("accounts:laporan_tim")), 'name="satuan"')


class FormTambahMatraTests(TestCase):
    """Form Tambah asks a superadmin the matra; the vehicle keeps it."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_superuser(username="root_matra", password="rahasia-123")
        self.client.login(username="root_matra", password="rahasia-123")

    def test_page_offers_the_three_matra(self):
        response = self.client.get(reverse("accounts:form_tambah"))
        for label in ("Matra Darat", "Matra Laut", "Matra Udara"):
            self.assertContains(response, label)
        # The vehicle groups show for Matra Darat only; Laut and Udara are empty.
        self.assertContains(response, """x-show="tab === 'kendaraan' && matra === 'darat'\"""")
        self.assertContains(response, "Belum ada jenis kendaraan untuk matra ini.")

    def test_others_add_for_their_own_matra(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import AkunPublik
        user = User.objects.create_user(username="anggota_matra", password="rahasia-123")
        AkunPublik.objects.update_or_create(user=user, defaults={"matra": "udara"})
        self.client.login(username="anggota_matra", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:form_tambah")), "Matra Laut")
        fotos = [SimpleUploadedFile(f"f{i}.gif", TINY_GIF, content_type="image/gif") for i in range(4)]
        self.client.post(
            reverse("fleet:vehicle_create") + "?group=B&matra=laut",
            {"kepemilikan": "organik", "nopol": "B 9 MT", "merek": "Isuzu", "foto": fotos}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(Vehicle.objects.get(nopol="B 9 MT").matra, "udara")

    def test_vehicle_keeps_the_matra_picked(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        url = reverse("fleet:vehicle_create") + "?group=B&matra=laut"
        self.assertContains(self.client.get(url, HTTP_HX_REQUEST="true"), "matra=laut")
        for nopol, query, matra in (("B 1 MT", "&matra=laut", "laut"), ("B 2 MT", "&matra=angkasa", ""), ("B 3 MT", "", "")):
            fotos = [SimpleUploadedFile(f"f{i}.gif", TINY_GIF, content_type="image/gif") for i in range(4)]
            self.client.post(
                reverse("fleet:vehicle_create") + "?group=B" + query,
                {"kepemilikan": "organik", "nopol": nopol, "merek": "Isuzu", "foto": fotos}, HTTP_HX_REQUEST="true",
            )
            self.assertEqual(Vehicle.objects.get(nopol=nopol).matra, matra)
