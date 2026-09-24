from . import roles


def menu(request):
    """Sidebar menus the current user may see (``menu_boleh``)."""
    user = getattr(request, "user", None)
    return {"menu_boleh": roles.allowed_menus(user) if user is not None else frozenset()}
