"""Backup menu (superuser only): make, list, download and delete backups of
the database, alone or zipped together with the uploaded photos."""
import re
import sqlite3
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.db import connection
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

# backup-<yyyymmdd>-<hhmmss>-<database|lengkap>.<ext>: the only names served or deleted.
POLA_NAMA = re.compile(r"^backup-\d{8}-\d{6}-(database|lengkap)\.(sqlite3|json|zip)$")
JENIS = {"database": "Database", "lengkap": "Database + foto"}


def _superuser(request):
    if not request.user.is_superuser:
        raise Http404


def _dir():
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _salin_database(tujuan):
    """A consistent copy of the database at ``tujuan`` (without its suffix):
    SQLite's own online backup, or a JSON dump for any other engine. Returns the file."""
    if connection.vendor == "sqlite":
        berkas = tujuan.with_suffix(".sqlite3")
        connection.ensure_connection()
        salinan = sqlite3.connect(berkas)
        try:
            connection.connection.backup(salinan)
        finally:
            salinan.close()
        return berkas
    berkas = tujuan.with_suffix(".json")
    with open(berkas, "w", encoding="utf-8") as f:
        call_command("dumpdata", "--natural-foreign", "--exclude", "contenttypes", "--exclude", "sessions", stdout=f)
    return berkas


def buat(jenis):
    """Make a backup now; ``jenis``: "database", or "lengkap" for a zip of the
    database and every uploaded photo. Returns the file."""
    nama = f"backup-{timezone.localtime():%Y%m%d-%H%M%S}-{jenis}"
    database = _salin_database(_dir() / nama)
    if jenis != "lengkap":
        return database
    arsip = _dir() / f"{nama}.zip"
    with zipfile.ZipFile(arsip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(database, f"database{database.suffix}")
        for foto in _semua_media():
            with default_storage.open(foto, "rb") as f:
                # Photos are JPEG already: stored as they are, not squeezed again.
                z.writestr(zipfile.ZipInfo.from_file(database, f"media/{foto}"), f.read(), zipfile.ZIP_STORED)
    database.unlink()
    return arsip


def _semua_media(awalan=""):
    """Names of every uploaded file, wherever the storage keeps them (the
    disk, or the Garage bucket in production), sorted."""
    try:
        folder, berkas = default_storage.listdir(awalan)
    except (FileNotFoundError, NotADirectoryError):
        return []
    hasil = [f"{awalan}{nama}" for nama in berkas if nama]
    for nama in folder:
        if nama:
            hasil += _semua_media(f"{awalan}{nama}/")
    return sorted(hasil)


def daftar():
    """The backups on disk, newest first."""
    hasil = []
    for berkas in _dir().iterdir():
        cocok = POLA_NAMA.match(berkas.name)
        if cocok and berkas.is_file():
            info = berkas.stat()
            hasil.append({
                "nama": berkas.name, "jenis": JENIS[cocok.group(1)], "ukuran": info.st_size,
                "waktu": timezone.datetime.fromtimestamp(info.st_mtime, tz=timezone.get_current_timezone()),
            })
    return sorted(hasil, key=lambda b: b["nama"], reverse=True)


def _berkas(nama):
    """The backup file called ``nama``, or 404 (also for anything that isn't a backup's name)."""
    berkas = _dir() / nama
    if not POLA_NAMA.match(nama) or not berkas.is_file():
        raise Http404
    return berkas


@login_required
def backup_view(request):
    _superuser(request)
    semua = daftar()
    return render(request, "accounts/backup.html", {
        "backup_list": semua, "total": sum(b["ukuran"] for b in semua), "folder": _dir(),
    })


@login_required
@require_POST
def backup_buat(request):
    _superuser(request)
    jenis = request.POST.get("jenis")
    if jenis not in JENIS:
        raise Http404
    try:
        berkas = buat(jenis)
    except (OSError, sqlite3.Error) as galat:
        messages.error(request, f"Backup gagal dibuat: {galat}")
    else:
        messages.success(request, f"Backup {berkas.name} berhasil dibuat.")
    return redirect("accounts:backup")


@login_required
def backup_unduh(request, nama):
    _superuser(request)
    return FileResponse(open(_berkas(nama), "rb"), as_attachment=True, filename=nama)


@login_required
def backup_hapus(request, nama):
    """GET: confirmation for the modal. POST: delete the backup file."""
    _superuser(request)
    berkas = _berkas(nama)
    if request.method == "POST":
        berkas.unlink()
        messages.success(request, f"Backup {nama} berhasil dihapus.")
        return redirect("accounts:backup")
    return render(request, "accounts/_backup_hapus.html", {"nama": nama})
