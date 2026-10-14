"""Keanggotaan (membership) of app users.

Superuser is Django's is_superuser flag; the other roles are auth Groups
(created by migrations 0006, 0012, 0058, 0061 and 0067), one per user. Tim members hang under a
Ketua Tim in the Anggota tree (django-treebeard).
"""

# Password every user created from Pengaturan starts with.
DEFAULT_PASSWORD = "12345"

SUPERUSER = "superuser"
ADMIN_ROLE = "admin"
KETUA_TIM = "ketua_tim"
PIMPINAN_TIM = "pimpinan_tim"

KEANGGOTAAN = [
    (SUPERUSER, "Superuser"),
    (ADMIN_ROLE, "Admin"),
    ("pimpinan", "Pimpinan"),
    # A Pimpinan over chosen teams only: they pick the Ketua Tim under them
    # (models.BawahanPimpinan) and see those teams' work.
    (PIMPINAN_TIM, "Pimpinan Ketua Tim"),
    (KETUA_TIM, "Ketua Tim"),
    ("tim_pemeriksaan", "Tim Pemeriksaan"),
    ("tim_penambahan_data", "Tim Penambahan Data"),
    ("tim_perbaikan", "Tim Perbaikan"),
    # Declares vehicles beyond use with Form Rusak/Tidak Layak Pakai.
    ("tim_tidak_layak", "Tim Pemeriksaan Rusak/Tidak Layak"),
]

# The service branch (AkunPublik.matra) of an Admin, a Ketua Tim and a Tim
# member, picked when they are made (see BERMATRA).
MATRA = [("darat", "Matra Darat"), ("laut", "Matra Laut"), ("udara", "Matra Udara")]

# Roles that must be placed under a Ketua Tim.
TIM = {"tim_pemeriksaan", "tim_penambahan_data", "tim_perbaikan", "tim_tidak_layak"}

# The admin roles, as a set: there is one (it used to be Admin Pusat and
# Admin Cabang), which owns the Ketua Tim it adds.
ADMIN = {ADMIN_ROLE}

# The roles that have a matra, and must be given one.
BERMATRA = {ADMIN_ROLE, KETUA_TIM, PIMPINAN_TIM, *TIM}

# Admin roles form a ladder: a role on it is given, changed or deleted only
# by someone higher up (Superuser > Admin). A Pimpinan stands beside the
# Admin: only a superuser makes, changes or deletes one. Roles off the ladder
# are open to anyone who can reach Pengaturan.
TINGKAT = {SUPERUSER: 3, ADMIN_ROLE: 2, "pimpinan": 2}

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


def boleh_kelola(kode_pengelola, kode):
    """Whether a user with role ``kode_pengelola`` may give role ``kode`` to
    someone, or change or delete a user who has it."""
    if kode_pengelola == SUPERUSER:
        return True
    tingkat = TINGKAT.get(kode, 0)
    return tingkat == 0 or tingkat < TINGKAT.get(kode_pengelola, 0)


# Sidebar menu -> URL names that belong to it (pages plus the endpoints
# those pages call). A view listed nowhere (login, logout, admin, ...) is
# not restricted by menu.
MENU_VIEWS = {
    "dashboard": {"accounts:dashboard", "accounts:dashboard_partial", "accounts:dashboard_kendaraan"},
    "armada": {
        "fleet:vehicle_list", "fleet:vehicle_create", "fleet:vehicle_update",
        "fleet:vehicle_delete", "fleet:vehicle_delete_confirm", "fleet:vehicle_photos",
        "fleet:vehicle_qr_modal", "fleet:vehicle_search", "accounts:history_kendaraan_modal",
    },
    "non_kendaraan": {
        "accounts:non_kendaraan", "accounts:non_kendaraan_create", "accounts:non_kendaraan_update",
        "accounts:non_kendaraan_delete",
    },
    "info_profile": {"accounts:info_profile", "accounts:info_profile_edit"},
    "anggota_tim": {
        "accounts:anggota_tim", "accounts:anggota_tim_tambah", "accounts:anggota_tim_ubah",
        "accounts:anggota_tim_vpn", "accounts:anggota_tim_vpn_hapus", "accounts:anggota_tim_aktif",
        "accounts:pimpinan_tim_bawahan",
        "accounts:vpn_download", "accounts:vpn_config",
    },
    "rekap_kerusakan": {"accounts:rekap_kerusakan"},
    "pemeriksaan": {
        "accounts:pemeriksaan", "accounts:pemeriksaan_captcha", "accounts:pemeriksaan_checklist", "accounts:pemeriksaan_draft",
        "accounts:pemeriksaan_lain",
        "fleet:vehicle_lookup",
    },
    # Form Tambah adds the vehicle through the Armada create modal.
    "form_tambah": {"accounts:form_tambah", "fleet:vehicle_create"},
    "history": {
        "accounts:history", "accounts:history_kendaraan", "accounts:history_kendaraan_modal", "fleet:vehicle_qr",
    },
    "perbaikan": {"accounts:perbaikan", "accounts:perbaikan_kendaraan", "accounts:perbaikan_draft"},
    # Form Rusak/Tidak Layak Pakai: declares a vehicle beyond repair.
    "rusak": {"accounts:rusak", "accounts:rusak_kendaraan"},
    "status": {"accounts:status", "accounts:status_batal"},
    "laporan_pemeriksaan": {
        "accounts:laporan_pemeriksaan", "accounts:laporan_pemeriksaan_detail", "accounts:laporan_pemeriksaan_pdf",
        "accounts:laporan_hapus",
        "fleet:vehicle_qr", "fleet:vehicle_qr_modal",
    },
    "laporan_perbaikan": {
        "accounts:laporan_perbaikan", "accounts:laporan_perbaikan_detail", "accounts:laporan_perbaikan_pdf",
        "accounts:laporan_hapus",
        "fleet:vehicle_qr", "fleet:vehicle_qr_modal",
    },
    "laporan_rusak": {
        "accounts:laporan_rusak", "accounts:laporan_rusak_detail", "accounts:laporan_hapus",
        "fleet:vehicle_qr", "fleet:vehicle_qr_modal",
    },
    "laporan_penambahan": {
        "accounts:laporan_penambahan", "accounts:laporan_penambahan_detail", "accounts:laporan_penambahan_pdf",
        "fleet:vehicle_qr", "fleet:vehicle_qr_modal",
        "accounts:laporan_hapus",
    },
    "laporan_tim": {"accounts:laporan_tim", "accounts:laporan_tim_detail", "accounts:laporan_tim_pdf", "accounts:laporan_anggota_pdf"},
    "pengaturan": {
        "accounts:pengaturan", "accounts:user_create", "accounts:user_delete", "accounts:user_edit",
        "accounts:user_reset_password", "accounts:km_jadwal_edit",
        "accounts:satuan_create", "accounts:satuan_update", "accounts:satuan_delete",
        "accounts:satuan_ekspor", "accounts:satuan_impor",
        "accounts:pimpinan_tim_bawahan",
        "accounts:vpn_download", "accounts:vpn_config",
    },
    "server": {"accounts:server", "accounts:server_partial"},
    "backup": {"accounts:backup", "accounts:backup_buat", "accounts:backup_unduh", "accounts:backup_hapus",
               "accounts:backup_unggah", "accounts:backup_pulihkan"},
    "form_group": {
        "accounts:form_group", "accounts:form_group_lihat", "accounts:form_group_tambah",
        "accounts:form_group_hapus",
    },
}
ALL_MENUS = frozenset(MENU_VIEWS)

# Menus only a superuser sees.
MENU_SUPERUSER = frozenset({"form_group", "server", "backup", "armada", "non_kendaraan"})
# Menus only the Tim roles (their own work in progress), the admins (their
# Tim members' work) and superusers (every Tim member's) see.
MENU_TIM = frozenset({"status"})

# The forms of Form Tambah a Tim Penambahan Data member can be given in Form
# Group: the vehicle groups (fleet Vehicle.GroupKendaraan values) and the
# Non Kendaraan tab.
FORM_TAMBAH = [
    ("B", 'Golongan "B"'),
    ("bermotor", "Motor"),
    ("diesel", "Kendaraan Diesel"),
    ("jeep", "Jeep Diesel"),
    ("ranpur", "RANPUR"),
    ("rantis", "RANTIS"),
    ("ransus", "RANSUS"),
    ("ranum", "RANUM"),
    ("non_kendaraan", "Non Kendaraan"),
]

# Roles limited to some menus; every other role (and a user without one)
# sees everything but MENU_SUPERUSER.
MENU_PER_KEANGGOTAAN = {
    # Admins see everything except the three Tim forms (dashboard first: it's home).
    **dict.fromkeys(ADMIN, ["dashboard"] + [
        m for m in MENU_VIEWS if m not in {"dashboard", "pemeriksaan", "form_tambah", "perbaikan", "rusak"}
    ]),
    # A Pimpinan sees every menu but the Tim forms, Status and Pengaturan
    # (and the superuser's menus, taken out for every role).
    "pimpinan": ["dashboard"] + [
        m for m in MENU_VIEWS
        if m not in {"dashboard", "pemeriksaan", "form_tambah", "perbaikan", "rusak", "pengaturan"} | MENU_TIM
    ],
    # A Pimpinan Tim looks at their teams; they don't manage users or forms.
    PIMPINAN_TIM: [
        "dashboard", "info_profile", "history", "anggota_tim", "laporan_pemeriksaan", "laporan_perbaikan",
        "laporan_rusak", "laporan_penambahan", "laporan_tim",
    ],
    # A Ketua Tim sees what each of the three Tim roles sees.
    KETUA_TIM: [
        "info_profile", "dashboard", "history", "anggota_tim", "laporan_pemeriksaan", "laporan_perbaikan",
        "laporan_rusak", "laporan_penambahan", "laporan_tim",
    ],
    "tim_pemeriksaan": ["info_profile", "pemeriksaan", "history", "status"],
    "tim_penambahan_data": ["info_profile", "form_tambah", "history", "status"],
    "tim_perbaikan": ["info_profile", "perbaikan", "history", "status"],
    "tim_tidak_layak": ["info_profile", "rusak", "history", "status"],
}

# Where each menu's page lives, used to send a user to their first menu.
MENU_HOME = {
    "dashboard": "accounts:dashboard",
    "armada": "fleet:vehicle_list",
    "non_kendaraan": "accounts:non_kendaraan",
    "info_profile": "accounts:info_profile",
    "anggota_tim": "accounts:anggota_tim",
    "rekap_kerusakan": "accounts:rekap_kerusakan",
    "pemeriksaan": "accounts:pemeriksaan",
    "form_tambah": "accounts:form_tambah",
    "history": "accounts:history",
    "perbaikan": "accounts:perbaikan",
    "rusak": "accounts:rusak",
    "status": "accounts:status",
    "laporan_pemeriksaan": "accounts:laporan_pemeriksaan",
    "laporan_perbaikan": "accounts:laporan_perbaikan",
    "laporan_rusak": "accounts:laporan_rusak",
    "laporan_penambahan": "accounts:laporan_penambahan",
    "laporan_tim": "accounts:laporan_tim",
    "pengaturan": "accounts:pengaturan",
    "form_group": "accounts:form_group",
    "server": "accounts:server",
    "backup": "accounts:backup",
}


def _menu_user(user):
    """Menus of the user's role in order (the first is home), or None for all."""
    menus = MENU_PER_KEANGGOTAAN.get(keanggotaan_kode(user))
    return [m for m in menus if m not in MENU_SUPERUSER] if menus else None


def allowed_menus(user):
    if not user.is_authenticated:
        return frozenset()
    if user.is_superuser:
        return ALL_MENUS
    menus = _menu_user(user)
    return frozenset(menus) if menus else ALL_MENUS - MENU_SUPERUSER - MENU_TIM


def home_view_name(user):
    menus = _menu_user(user)
    return MENU_HOME[menus[0]] if menus else MENU_HOME["dashboard"]


def form_tambah_boleh(user):
    """FORM_TAMBAH keys the user may open in Form Tambah, as set in Form
    Group: for this user, else for their Ketua Tim's team, else all of them."""
    from .models import AksesFormTambah, Anggota
    semua = [kode for kode, _ in FORM_TAMBAH]
    akses = AksesFormTambah.objects.filter(user=user).values_list("form", flat=True).first()
    if akses is None:
        node = Anggota.objects.filter(user=user).first()
        if node is not None and not node.is_root():
            akses = AksesFormTambah.objects.filter(user_id=node.get_parent().user_id).values_list("form", flat=True).first()
    return semua if akses is None else [kode for kode in semua if kode in akses]


def menus_of_view(view_name):
    """Menus a view belongs to (a view may serve more than one menu)."""
    return {menu for menu, names in MENU_VIEWS.items() if view_name in names}
