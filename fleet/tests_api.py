from django.conf import settings
from django.contrib.auth.models import User
from django.test import TransactionTestCase

from django_bolt.auth import create_token_pair
from django_bolt.testing import TestClient

from fleet.api import api
from fleet.models import Vehicle


def _auth_headers(user):
    pair = create_token_pair(user, secret=settings.SECRET_KEY, method="pwd")
    return {"Authorization": f"Bearer {pair.access_token}"}


class VehicleApiAuthTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_list_without_token_returns_401(self):
        with TestClient(api) as client:
            response = client.get("/api/vehicles")
        self.assertEqual(response.status_code, 401)

    def test_create_without_token_returns_401(self):
        with TestClient(api) as client:
            response = client.post("/api/vehicles", json={"nopol": "B 1234 AB"})
        self.assertEqual(response.status_code, 401)


class VehicleApiCrudTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.headers = _auth_headers(self.user)

    def test_create_list_retrieve_update_delete_round_trip(self):
        with TestClient(api) as client:
            create_response = client.post(
                "/api/vehicles",
                headers=self.headers,
                json={
                    "nopol": "B 1234 AB",
                    "jenis": "mobil",
                    "merek": "Toyota Avanza",
                    "tahun": 2021,
                    "status": "siap_pakai",
                    "odometer_km": 1000,
                    "penanggung_jawab": "Siti Amalia",
                },
            )
            self.assertEqual(create_response.status_code, 201)
            vehicle_id = create_response.json()["id"]

            list_response = client.get("/api/vehicles", headers=self.headers)
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()), 1)

            retrieve_response = client.get(f"/api/vehicles/{vehicle_id}", headers=self.headers)
            self.assertEqual(retrieve_response.status_code, 200)
            self.assertEqual(retrieve_response.json()["nopol"], "B 1234 AB")

            update_response = client.put(
                f"/api/vehicles/{vehicle_id}",
                headers=self.headers,
                json={
                    "nopol": "B 1234 AB",
                    "jenis": "mobil",
                    "merek": "Toyota Avanza",
                    "tahun": 2021,
                    "status": "dalam_perbaikan",
                    "odometer_km": 2000,
                    "penanggung_jawab": "Siti Amalia",
                },
            )
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(update_response.json()["status"], "dalam_perbaikan")

            delete_response = client.delete(f"/api/vehicles/{vehicle_id}", headers=self.headers)
            self.assertEqual(delete_response.status_code, 204)

        self.assertEqual(Vehicle.objects.count(), 0)

    def test_retrieve_nonexistent_returns_404(self):
        with TestClient(api) as client:
            response = client.get("/api/vehicles/9999", headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_create_duplicate_nopol_returns_409(self):
        Vehicle.objects.create(
            nopol="B 1234 AB", jenis=Vehicle.Jenis.MOBIL, merek="Toyota Avanza",
            tahun=2021, status=Vehicle.Status.SIAP_PAKAI, odometer_km=1000,
            penanggung_jawab="Siti Amalia",
        )
        with TestClient(api) as client:
            response = client.post(
                "/api/vehicles",
                headers=self.headers,
                json={
                    "nopol": "B 1234 AB",
                    "jenis": "mobil",
                    "merek": "Toyota Avanza 2",
                    "tahun": 2022,
                    "status": "siap_pakai",
                    "odometer_km": 500,
                    "penanggung_jawab": "Budi Santoso",
                },
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_partial_update_not_available(self):
        vehicle = Vehicle.objects.create(
            nopol="B 5555 CD", jenis=Vehicle.Jenis.MOBIL, merek="Test",
            tahun=2020, status=Vehicle.Status.SIAP_PAKAI, odometer_km=0,
            penanggung_jawab="Test",
        )
        with TestClient(api) as client:
            response = client.patch(f"/api/vehicles/{vehicle.id}", headers=self.headers, json={"odometer_km": 999})
        self.assertEqual(response.status_code, 404)


class FleetSummaryApiTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        self.headers = _auth_headers(self.user)

    def test_summary_without_token_returns_401(self):
        with TestClient(api) as client:
            response = client.get("/api/fleet/summary")
        self.assertEqual(response.status_code, 401)

    def test_summary_matches_get_fleet_summary(self):
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
        with TestClient(api) as client:
            response = client.get("/api/fleet/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"total": 2, "ready": 1, "in_repair": 1, "due_soon": 0},
        )

    def test_summary_on_empty_fleet(self):
        with TestClient(api) as client:
            response = client.get("/api/fleet/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"total": 0, "ready": 0, "in_repair": 0, "due_soon": 0},
        )
