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
        versi = {"css_version": int(os.path.getmtime(path))}
    except (TypeError, OSError):
        versi = {"css_version": ""}
    # Same for the app's own scripts (static/js/*.js), which change with features.
    js = [finders.find(f"js/{nama}") for nama in ("qr-scan.js", "autocomplete.js")]
    try:
        versi["js_version"] = max(int(os.path.getmtime(p)) for p in js if p)
    except (ValueError, OSError):
        versi["js_version"] = ""
    return versi
