from django.test import TestCase

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
