import os

from django.contrib.staticfiles import finders

from . import roles

# The roles whose menus wait for their biodata (Info Profil): the Tim members,
# whose forms record it on every inspection, repair or addition. A Ketua Tim
# manages a team and reads reports: History and Anggota Tim open right away.
_TIM_ROLES = roles.TIM


# The phone's bottom bar: the first four of these the user may open, with a
# short label; the rest of the menu is one tap away under "Menu".
MENU_BAWAH = [
    ("dashboard", "Dashboard"), ("pemeriksaan", "Periksa"), ("perbaikan", "Perbaikan"),
    ("form_tambah", "Tambah"), ("rusak", "Rusak"), ("history", "History"), ("anggota_tim", "Tim"),
    ("aktivasi_ketua_tim", "Aktivasi"), ("rekap_kerusakan", "Rekap"), ("status", "Status"),
    ("info_profile", "Profil"), ("laporan_pemeriksaan", "Laporan"),
]
# Menus that wait for the biodata (templates/base.html greys them out).
_TUNGGU_PROFIL = {"pemeriksaan", "perbaikan", "form_tambah", "rusak", "history", "anggota_tim"}


def _menu_bawah(boleh, profil_belum_isi):
    from django.urls import reverse

    return [
        {"kunci": k, "label": label, "url": reverse(roles.MENU_HOME[k]),
         "terkunci": profil_belum_isi and k in _TUNGGU_PROFIL}
        for k, label in MENU_BAWAH if k in boleh
    ][:4]


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
    boleh = roles.allowed_menus(user) if user is not None else frozenset()
    aktivasi_menunggu = 0
    if "aktivasi_ketua_tim" in boleh:
        from .aktivasi import jumlah_menunggu
        aktivasi_menunggu = jumlah_menunggu(user)
    return {
        # Sign-ups waiting for activation: the badge on Aktivasi Ketua Tim.
        "aktivasi_menunggu": aktivasi_menunggu,
        "menu_boleh": boleh,
        "menu_aktif": menu_aktif,
        "profil_belum_isi": profil_belum_isi,
        "menu_bawah": _menu_bawah(boleh, profil_belum_isi) if user is not None and user.is_authenticated else [],
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
    js = [finders.find(f"js/{nama}") for nama in ("qr-scan.js", "autocomplete.js", "datepicker.js", "kompres-foto.js", "skeleton.js", "geser.js", "modal-halus.js", "tombol-proses.js", "server-sibuk.js")]
    try:
        versi["js_version"] = max(int(os.path.getmtime(p)) for p in js if p)
    except (ValueError, OSError):
        versi["js_version"] = ""
    return versi
