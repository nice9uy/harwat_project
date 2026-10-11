import os

from django.contrib.staticfiles import finders

from . import roles

_TIM_ROLES = roles.TIM | {roles.KETUA_TIM}


def menu(request):
    """Sidebar menus the current user may see (``menu_boleh``)."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    view_name = match.view_name if match else ""
    menu_aktif = next((m for m in roles.MENU_VIEWS if view_name in roles.MENU_VIEWS[m]), "")
    if view_name == "accounts:ganti_password":
        menu_aktif = "ganti_password"
    profil_belum_isi = False
    if user is not None and user.is_authenticated and roles.keanggotaan_kode(user) in _TIM_ROLES:
        from .models import Laporan
        profil_belum_isi = not Laporan.objects.filter(akun=user).exists()
    return {
        "menu_boleh": roles.allowed_menus(user) if user is not None else frozenset(),
        "menu_aktif": menu_aktif,
        "profil_belum_isi": profil_belum_isi,
    }


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
    js = [finders.find(f"js/{nama}") for nama in ("qr-scan.js", "autocomplete.js", "datepicker.js", "kompres-foto.js", "skeleton.js")]
    try:
        versi["js_version"] = max(int(os.path.getmtime(p)) for p in js if p)
    except (ValueError, OSError):
        versi["js_version"] = ""
    return versi
