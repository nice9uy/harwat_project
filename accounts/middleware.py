from django.contrib import messages
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
