"""Keanggotaan (membership) of app users.

Superuser is Django's is_superuser flag; the other roles are auth Groups
(created by migration 0006), one per user.
"""

SUPERUSER = "superuser"
ADMIN = "admin"

KEANGGOTAAN = [
    (SUPERUSER, "Superuser"),
    (ADMIN, "Admin"),
    ("pimpinan", "Pimpinan"),
    ("petugas_pemeriksaan", "Petugas Pemeriksaan"),
    ("petugas_penambahan_data", "Petugas Penambahan Data"),
    ("petugas_perbaikan", "Petugas Perbaikan"),
]

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
