from functools import wraps
from inspect import iscoroutinefunction

from django.contrib import messages
from django.http import Http404, HttpResponseNotFound
from django.shortcuts import redirect

from . import roles


class MenuAccessMiddleware:
    """Keep Tim users inside their menus (see roles.MENU_PER_KEANGGOTAAN).

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
            raise Http404
        return self.get_response(request)


# Same text as Django's default 404 page, so the docs look like any missing URL.
NOT_FOUND = "<h1>Not Found</h1><p>The requested resource was not found on this server.</p>"


def superuser_only(view):
    """Decorator for the API docs (async Bolt handlers): 404 unless superuser."""
    # wraps() keeps the handler's signature, which Bolt reads to bind parameters.
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
