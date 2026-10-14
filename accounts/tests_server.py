"""Server menu: Podman containers and the machine's CPU, RAM and storage."""
import json
import os
import socketserver
import tempfile
import threading
from http.server import BaseHTTPRequestHandler

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import server


class _PodmanPalsu(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps([
            {"Names": ["db"], "State": "exited", "Image": "docker.io/library/postgres:17", "StartedAt": 0, "Ports": None},
            {"Names": ["app"], "State": "running", "Image": "localhost/app:latest", "StartedAt": 1790000000,
             "Ports": [{"host_port": 8001, "container_port": 8001}]},
        ]).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def address_string(self):
        return "unix"

    def log_message(self, *args):
        pass


class ServerTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.url = reverse("accounts:server")

    def test_superuser_only(self):
        self.assertContains(self.client.get(self.url), f'<a href="{self.url}" class=')
        admin = User.objects.create_user(username="pusat", password="rahasia-123")
        admin.groups.add(Group.objects.get(name="Admin"))
        self.client.login(username="pusat", password="rahasia-123")
        self.assertNotContains(self.client.get(reverse("accounts:dashboard")), f'href="{self.url}"')
        for nama in ("accounts:server", "accounts:server_partial"):
            self.assertNotEqual(self.client.get(reverse(nama)).status_code, 200)

    @override_settings(PODMAN_SOCKET="/tidak/ada/podman.sock")
    def test_resources_shown_and_refreshed_even_without_podman(self):
        response = self.client.get(self.url)
        for text in ("CPU", "RAM", "Storage", "Kontainer Podman", "Socket Podman tidak ditemukan",
                     f'hx-get="{reverse("accounts:server_partial")}"', f'hx-trigger="every {server.JEDA_DETIK}s"'):
            self.assertContains(response, text)
        partial = self.client.get(reverse("accounts:server_partial"))
        self.assertContains(partial, "Diperbarui otomatis")
        self.assertNotContains(partial, "<html")

    def test_measurements_are_sane(self):
        cpu, ram, storage = server.cpu(), server.ram(), server.storage()
        self.assertTrue(0 <= cpu["persen"] <= 100 and cpu["inti"] >= 1)
        self.assertTrue(0 < ram["terpakai"] < ram["total"])
        self.assertTrue(storage and all(0 < s["terpakai"] <= s["total"] for s in storage))

    def test_lists_containers_from_the_podman_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "podman.sock")
            with socketserver.UnixStreamServer(path, _PodmanPalsu) as palsu:
                threading.Thread(target=palsu.serve_forever, daemon=True).start()
                try:
                    with override_settings(PODMAN_SOCKET=path):
                        daftar, galat = server.kontainer()
                        response = self.client.get(reverse("accounts:server_partial"))
                finally:
                    palsu.shutdown()
        self.assertEqual(galat, "")
        # Running containers first.
        self.assertEqual([(k["nama"], k["hidup"], k["image"], k["port"]) for k in daftar],
                         [("app", True, "app:latest", "8001→8001"), ("db", False, "postgres:17", "")])
        self.assertContains(response, "1 hidup dari 2")
        self.assertContains(response, "Mati (exited)")

    def test_lists_containers_through_the_read_only_relay(self):
        # Production: the app asks the podman-api relay over TCP, never the socket.
        with socketserver.TCPServer(("127.0.0.1", 0), _PodmanPalsu) as palsu:
            threading.Thread(target=palsu.serve_forever, daemon=True).start()
            try:
                with override_settings(PODMAN_API=f"http://127.0.0.1:{palsu.server_address[1]}", PODMAN_SOCKET="/tidak/ada.sock"):
                    daftar, galat = server.kontainer()
            finally:
                palsu.shutdown()
        self.assertEqual((galat, [k["nama"] for k in daftar]), ("", ["app", "db"]))
