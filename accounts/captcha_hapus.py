"""A code to retype before anything is deleted (templates/_captcha_hapus.html):
the confirmation dialog shows a fresh 6-digit code, kept in the session under
the thing being deleted; the delete goes ahead only with that code, once."""
import secrets
import string

from django.contrib import messages


def _kunci(nama):
    return f"captcha_hapus:{nama}"


def buat(request, nama):
    """A new code for deleting ``nama`` (e.g. "kendaraan:<uuid>")."""
    kode = "".join(secrets.choice(string.digits) for _ in range(6))
    request.session[_kunci(nama)] = kode
    return kode


def cocok(request, nama):
    """Whether the POST carries the code shown for ``nama`` (used up either
    way); says so when it doesn't."""
    benar = request.session.pop(_kunci(nama), None)
    if benar and request.POST.get("captcha", "").strip() == benar:
        return True
    messages.error(request, "Kode verifikasi salah, data tidak dihapus. Coba lagi.")
    return False
