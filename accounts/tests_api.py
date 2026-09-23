from django.contrib.auth.models import User
from django.test import TransactionTestCase

from django_bolt.testing import TestClient

from accounts.api import api


class LoginRouteTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")

    def test_valid_credentials_returns_token_pair(self):
        with TestClient(api) as client:
            response = client.post(
                "/auth/login", json={"username": "teknisi1", "password": "rahasia-123"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)
        self.assertEqual(body["token_type"], "bearer")

    def test_invalid_credentials_returns_401(self):
        with TestClient(api) as client:
            response = client.post(
                "/auth/login", json={"username": "teknisi1", "password": "salah"}
            )
        self.assertEqual(response.status_code, 401)


class RefreshAndLogoutRouteTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="rahasia-123")
        with TestClient(api) as client:
            login_response = client.post(
                "/auth/login", json={"username": "teknisi1", "password": "rahasia-123"}
            )
        self.refresh_token = login_response.json()["refresh_token"]

    def test_refresh_returns_new_pair(self):
        with TestClient(api) as client:
            response = client.post(
                "/auth/refresh",
                headers={"Authorization": f"Bearer {self.refresh_token}"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)

    def test_logout_revokes_refresh_token(self):
        with TestClient(api) as client:
            logout_response = client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {self.refresh_token}"},
            )
            self.assertEqual(logout_response.status_code, 200)

            reuse_response = client.post(
                "/auth/refresh",
                headers={"Authorization": f"Bearer {self.refresh_token}"},
            )
        self.assertEqual(reuse_response.status_code, 401)

    def test_refresh_without_authorization_header_returns_401(self):
        with TestClient(api) as client:
            response = client.post("/auth/refresh")
        self.assertEqual(response.status_code, 401)

    def test_refresh_with_malformed_token_returns_401(self):
        with TestClient(api) as client:
            response = client.post(
                "/auth/refresh",
                headers={"Authorization": "Bearer garbage.garbage.garbage"},
            )
        self.assertEqual(response.status_code, 401)

    def test_logout_without_authorization_header_returns_401(self):
        with TestClient(api) as client:
            response = client.post("/auth/logout")
        self.assertEqual(response.status_code, 401)
