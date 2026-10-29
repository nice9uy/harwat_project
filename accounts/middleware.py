from functools import wraps
from inspect import iscoroutinefunction

from django.contrib import messages
from django.contrib.auth import login
from django.db.models import Q
from django.http import Http404, HttpResponseNotFound
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from . import roles
from .models import VpnPeer


class MenuAccessMiddleware:
    """Keep users inside their role's menus (see roles.allowed_menus).

    Hiding a menu in the sidebar isn't enough: the URL would still work,
    so views belonging to a menu the user may not see redirect to the
    user's first allowed menu.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or request.resolver_match is None:
            return None
        menus = roles.menus_of_view(request.resolver_match.view_name)
        if not menus or menus & roles.allowed_menus(request.user):
            return None
        home = roles.home_view_name(request.user)
        # The dashboard is just the default landing page; no error for it.
        if menus != {"dashboard"}:
            messages.error(request, "Anda tidak memiliki akses ke menu tersebut.")
        return redirect(home)


def _superuser(user):
    return user.is_active and user.is_superuser


class SuperuserOnlyAdminMiddleware:
    """Django admin is for superusers only; everyone else (signed in or not)
    gets a 404, as if it didn't exist."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/") and not _superuser(request.user):
            from .keamanan import catat
            from .models import AktivitasMencurigakan as A
            catat(request, A.Jenis.AKSES_ADMIN, A.Tingkat.SEDANG, "Bukan superuser")
            raise Http404
        return self.get_response(request)


# Same text as Django's default 404 page, so the docs look like any missing URL.
NOT_FOUND = "<h1>Not Found</h1><p>The requested resource was not found on this server.</p>"


def superuser_only(view):
    """Decorator for the API docs (async Bolt handlers): 404 unless superuser."""
    if iscoroutinefunction(view):
        @wraps(view)
        async def wrapper(request, *args, **kwargs):
            if not _superuser(await request.auser()):
                return HttpResponseNotFound(NOT_FOUND)
            return await view(request, *args, **kwargs)
    else:
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not _superuser(request.user):
                return HttpResponseNotFound(NOT_FOUND)
            return view(request, *args, **kwargs)
    return wrapper


class VpnAutoLoginMiddleware:
    """Auto-login anggota tim whose request comes from their registered WireGuard VPN IP.

    Only applies to TIM roles. Skipped if already authenticated or the account is switched off.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        if not settings.DEBUG and not request.user.is_authenticated:
            remote_ip = request.META.get("REMOTE_ADDR", "")
            if remote_ip:
                peer = self._find_peer(remote_ip)
                if peer and roles.keanggotaan_kode(peer.user) in roles.TIM:
                    peer.user.backend = "django.contrib.auth.backends.ModelBackend"
                    login(request, peer.user)
        return self.get_response(request)

    def _find_peer(self, remote_ip):
        peer = (
            VpnPeer.objects
            .filter(Q(client_ip=remote_ip) | Q(client_ip__startswith=remote_ip + "/"))
            .exclude(client_ip="")
            .filter(user__is_active=True)
            .select_related("user")
            .prefetch_related("user__groups")
            .first()
        )
        return peer


# Session key set at login when the password typed was roles.DEFAULT_PASSWORD.
WAJIB_GANTI_PASSWORD = "wajib_ganti_password"
_BOLEH_SEBELUM_GANTI = {"accounts:ganti_password", "accounts:logout", "accounts:login", "media", "manifest", "service_worker"}


class WajibGantiPasswordMiddleware:
    """Someone who logged in with the default password (roles.DEFAULT_PASSWORD)
    is kept on Ganti Password until they pick another one."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or not request.session.get(WAJIB_GANTI_PASSWORD):
            return None
        match = request.resolver_match
        if match is None or match.view_name in _BOLEH_SEBELUM_GANTI:
            return None
        url = reverse("accounts:ganti_password")
        if request.headers.get("HX-Request") == "true":
            response = HttpResponse(status=204)
            response["HX-Redirect"] = url
            return response
        messages.warning(request, "Anda masih memakai password bawaan. Ganti password dulu sebelum melanjutkan.")
        return redirect(url)
