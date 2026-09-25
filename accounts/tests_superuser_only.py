"""Django admin and the API docs exist only for superusers; everyone else gets a 404."""
import asyncio

from django.contrib.auth.models import AnonymousUser, Group, User
from django.test import TestCase

from accounts.middleware import superuser_only


class AdminSuperuserOnlyTests(TestCase):
    def test_superuser_opens_admin(self):
        User.objects.create_superuser(username="root", password="rahasia-123")
        self.client.login(username="root", password="rahasia-123")
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/fleet/vehicle/").status_code, 200)

    def test_everyone_else_gets_404(self):
        for path in ("/admin/", "/admin/login/", "/admin/fleet/vehicle/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        staff = User.objects.create_user(username="staf", password="rahasia-123", is_staff=True)
        staff.groups.add(Group.objects.get(name="Admin"))
        self.client.login(username="staf", password="rahasia-123")
        for path in ("/admin/", "/admin/fleet/vehicle/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class _Request:
    def __init__(self, user):
        self._user = user

    async def auser(self):
        return self._user


class ApiDocsSuperuserOnlyTests(TestCase):
    def test_docs_handler_only_runs_for_superusers(self):
        async def docs(request):
            return "docs"
        handler = superuser_only(docs)
        root = User(username="root", is_superuser=True, is_active=True)
        staf = User(username="staf", is_staff=True, is_active=True)
        self.assertEqual(asyncio.run(handler(_Request(root))), "docs")
        for user in (staf, AnonymousUser(), User(username="x", is_superuser=True, is_active=False)):
            self.assertEqual(asyncio.run(handler(_Request(user))).status_code, 404)

    def test_api_docs_use_the_guard(self):
        from harwat_main.api import api

        self.assertIs(api._openapi_config.django_auth, superuser_only)
