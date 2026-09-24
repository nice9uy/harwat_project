"""Keanggotaan (membership) of app users.

Superuser is Django's is_superuser flag; the other roles are auth Groups
(created by migrations 0006 and 0012), one per user. Tim members hang under a
Ketua Tim in the Anggota tree (django-treebeard).
"""

# Password every user created from Pengaturan starts with.
DEFAULT_PASSWORD = "12345"

SUPERUSER = "superuser"
ADMIN = "admin"
KETUA_TIM = "ketua_tim"

KEANGGOTAAN = [
    (SUPERUSER, "Superuser"),
    (ADMIN, "Admin"),
    ("pimpinan", "Pimpinan"),
    (KETUA_TIM, "Ketua Tim"),
    ("tim_pemeriksaan", "Tim Pemeriksaan"),
    ("tim_penambahan_data", "Tim Penambahan Data"),
    ("tim_perbaikan", "Tim Perbaikan"),
]

# Roles that must be placed under a Ketua Tim.
TIM = {"tim_pemeriksaan", "tim_penambahan_data", "tim_perbaikan"}

# Group name for every role except Superuser.
GROUP_NAMES = {kode: label for kode, label in KEANGGOTAAN if kode != SUPERUSER}


def keanggotaan_label(user):
    if user.is_superuser:
        return "Superuser"
    names = set(GROUP_NAMES.values())
    for group in user.groups.all():
        if group.name in names:
            return group.name
    return "-"


def keanggotaan_kode(user):
    if user.is_superuser:
        return SUPERUSER
    by_name = {label: kode for kode, label in GROUP_NAMES.items()}
    for group in user.groups.all():
        if group.name in by_name:
            return by_name[group.name]
    return None


# Sidebar menu -> URL names that belong to it (pages plus the endpoints
# those pages call). A view listed nowhere (login, logout, admin, ...) is
# not restricted by menu.
MENU_VIEWS = {
    "dashboard": {"accounts:dashboard", "accounts:dashboard_partial"},
    "armada": {
        "fleet:vehicle_list", "fleet:vehicle_create", "fleet:vehicle_update",
        "fleet:vehicle_delete", "fleet:vehicle_delete_confirm", "fleet:vehicle_photos",
        "fleet:vehicle_qr_modal", "fleet:vehicle_search",
    },
    "jadwal": set(),
    "servis": set(),
    "pemeriksaan": {
        "accounts:pemeriksaan", "accounts:pemeriksaan_captcha", "accounts:pemeriksaan_checklist",
        "fleet:vehicle_lookup",
    },
    # Form Tambah adds the vehicle through the Armada create modal.
    "form_tambah": {"accounts:form_tambah", "fleet:vehicle_create"},
    "history": {"accounts:history", "accounts:history_kendaraan", "fleet:vehicle_qr"},
    "perbaikan": {"accounts:perbaikan", "accounts:perbaikan_kendaraan"},
    "pengaturan": {
        "accounts:pengaturan", "accounts:user_create", "accounts:user_delete", "accounts:user_edit",
        "accounts:satuan_create", "accounts:satuan_update", "accounts:satuan_delete",
    },
}
ALL_MENUS = frozenset(MENU_VIEWS)

# Roles limited to some menus; every other role (and a user without one)
# sees everything.
MENU_PER_KEANGGOTAAN = {
    # A Ketua Tim sees what each of the three Tim roles sees.
    KETUA_TIM: ["pemeriksaan", "form_tambah", "perbaikan", "history"],
    "tim_pemeriksaan": ["pemeriksaan", "history"],
    "tim_penambahan_data": ["form_tambah", "history"],
    "tim_perbaikan": ["perbaikan", "history"],
}

# Where each menu's page lives, used to send a user to their first menu.
MENU_HOME = {
    "dashboard": "accounts:dashboard",
    "pemeriksaan": "accounts:pemeriksaan",
    "form_tambah": "accounts:form_tambah",
    "history": "accounts:history",
    "perbaikan": "accounts:perbaikan",
}


def allowed_menus(user):
    if not user.is_authenticated:
        return frozenset()
    menus = MENU_PER_KEANGGOTAAN.get(keanggotaan_kode(user))
    return frozenset(menus) if menus else ALL_MENUS


def home_view_name(user):
    menus = MENU_PER_KEANGGOTAAN.get(keanggotaan_kode(user))
    return MENU_HOME[menus[0]] if menus else MENU_HOME["dashboard"]


def menus_of_view(view_name):
    """Menus a view belongs to (a view may serve more than one menu)."""
    return {menu for menu, names in MENU_VIEWS.items() if view_name in names}
