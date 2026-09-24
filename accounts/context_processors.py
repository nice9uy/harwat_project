import os

from django.contrib.staticfiles import finders

from . import roles


def menu(request):
    """Sidebar menus the current user may see (``menu_boleh``)."""
    user = getattr(request, "user", None)
    return {"menu_boleh": roles.allowed_menus(user) if user is not None else frozenset()}


def css_version(request):
    """``css_version``: changes whenever static/dist/output.css is rebuilt.

    Appended to the stylesheet URL so browsers fetch the new file instead
    of a cached copy that lacks newly used Tailwind classes.
    """
    path = finders.find("dist/output.css")
    try:
        return {"css_version": int(os.path.getmtime(path))}
    except (TypeError, OSError):
        return {"css_version": ""}
