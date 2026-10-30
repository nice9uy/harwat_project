"""Backup menu (superuser only): make, list, download, upload and delete
backups (the database zipped together with the uploaded photos), and restore
one: put the data and the photos back as they were when it was made."""
import re
import sqlite3
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connection, transaction
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


def _nama_baru(jenis):
    """backup-<now>-<jenis>, a second later for as long as a backup of that
    name is there: two made within one second (the safety copy of a restore
    right after a backup) must not overwrite each other."""
    import datetime

    waktu = timezone.localtime()
    while True:
        nama = f"backup-{waktu:%Y%m%d-%H%M%S}-{jenis}"
        if not any(_dir().glob(f"{nama}.*")):
            return nama
        waktu += datetime.timedelta(seconds=1)


def buat(jenis):
    """Make a backup now; ``jenis``: "database", or "lengkap" for a zip of the
    database and every uploaded photo. Returns the file."""
    nama = _nama_baru(jenis)
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


# Typed into the restore form before anything is replaced.
KATA_PULIHKAN = "PULIHKAN"
# Kept through a restore from a JSON dump: the dump leaves content types and
# sessions out (and its permissions point at these very rows).
TABEL_TETAP = {"django_content_type", "auth_permission", "django_session", "django_migrations"}
DATABASE_DI_ZIP = ("database.sqlite3", "database.json")


class BackupTidakCocok(Exception):
    """The file is not a backup this installation can restore; says why."""


def _pulihkan_database(berkas):
    """Replace the database's contents with those of ``berkas``: a SQLite
    copy (only onto SQLite; migrated afterwards, in case it is from an older
    version) or a JSON dump (every table emptied, then loaded, all or nothing)."""
    if berkas.suffix == ".sqlite3":
        if connection.vendor != "sqlite":
            raise BackupTidakCocok("Backup ini berupa file SQLite, sedangkan aplikasi sekarang memakai PostgreSQL.")
        sumber = sqlite3.connect(f"file:{berkas}?mode=ro", uri=True)
        try:
            try:
                sumber.execute("select 1 from django_migrations limit 1")
            except sqlite3.Error:
                raise BackupTidakCocok("File ini bukan database aplikasi.") from None
            connection.ensure_connection()
            sumber.backup(connection.connection)
        finally:
            sumber.close()
        connection.close()
        call_command("migrate", "--noinput", verbosity=0)
        return
    with transaction.atomic():
        tabel = [
            t for t in connection.introspection.django_table_names(only_existing=True, include_views=False)
            if t not in TABEL_TETAP
        ]
        connection.ops.execute_sql_flush(
            connection.ops.sql_flush(no_style(), tabel, reset_sequences=True, allow_cascade=True)
        )
        # A dump from an older version may name fields that are gone since.
        call_command("loaddata", str(berkas), ignorenonexistent=True, verbosity=0)


def _pulihkan_media(arsip):
    """Put the photos of the open backup zip ``arsip`` back into the storage,
    over the ones of the same name. Photos uploaded since stay. Returns how many."""
    jumlah = 0
    for nama in arsip.namelist():
        if not nama.startswith("media/") or nama.endswith("/"):
            continue
        tujuan = nama[len("media/"):]
        if not tujuan or tujuan.startswith("/") or ".." in tujuan.split("/"):
            continue
        if default_storage.exists(tujuan):
            default_storage.delete(tujuan)
        default_storage.save(tujuan, ContentFile(arsip.read(nama)))
        jumlah += 1
    return jumlah


def pulihkan(berkas):
    """Restore the backup ``berkas`` (a zip of database and photos, or a
    database copy on its own). Returns how many photos were put back."""
    foto = 0
    if berkas.suffix == ".zip":
        with zipfile.ZipFile(berkas) as arsip:
            nama_db = next((n for n in DATABASE_DI_ZIP if n in arsip.namelist()), None)
            if nama_db is None:
                raise BackupTidakCocok("File zip ini tidak berisi database aplikasi.")
            sementara = _dir() / f".pulih-{uuid.uuid4().hex}{Path(nama_db).suffix}"
            try:
                with arsip.open(nama_db) as sumber, open(sementara, "wb") as tujuan:
                    while potongan := sumber.read(1024 * 1024):
                        tujuan.write(potongan)
                _pulihkan_database(sementara)
                foto = _pulihkan_media(arsip)
            finally:
                sementara.unlink(missing_ok=True)
    else:
        _pulihkan_database(berkas)
    # The WireGuard server's config follows the peers now in the database.
    from .vpn_utils import tulis_server_conf
    try:
        tulis_server_conf()
    except OSError:
        pass
    return foto


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
    # One button: everything (database and photos). "database" alone is
    # still made on request (redeploy.sh, before it replaces the containers).
    jenis = request.POST.get("jenis", "lengkap")
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
    from . import captcha_hapus

    berkas = _berkas(nama)
    if request.method == "POST":
        if not captcha_hapus.cocok(request, f"backup:{nama}"):
            return redirect("accounts:backup")
        berkas.unlink()
        messages.success(request, f"Backup {nama} berhasil dihapus.")
        return redirect("accounts:backup")
    return render(request, "accounts/_backup_hapus.html", {"nama": nama, "captcha_kode": captcha_hapus.buat(request, f"backup:{nama}")})


# Uploaded backups: at most this big (the app's own upload limit applies too).
UNGGAH_MAKS = 2 * 1024 * 1024 * 1024


@login_required
@require_POST
def backup_unggah(request):
    """Add a backup made elsewhere (downloaded here before, or from another
    server) to the list, from where it can be restored. Only a backup zip:
    one holding the database at its top."""
    _superuser(request)
    berkas = request.FILES.get("berkas")
    if berkas is None:
        messages.error(request, "Pilih file backup (.zip) terlebih dahulu.")
        return redirect("accounts:backup")
    if berkas.size > UNGGAH_MAKS:
        messages.error(request, "File backup terlalu besar.")
        return redirect("accounts:backup")
    tujuan = _dir() / f"{_nama_baru('lengkap')}.zip"
    with open(tujuan, "wb") as f:
        for potongan in berkas.chunks():
            f.write(potongan)
    try:
        with zipfile.ZipFile(tujuan) as arsip:
            sah = any(n in arsip.namelist() for n in DATABASE_DI_ZIP)
    except zipfile.BadZipFile:
        sah = False
    if not sah:
        tujuan.unlink(missing_ok=True)
        messages.error(request, "File itu bukan backup aplikasi ini (harus file .zip hasil unduhan menu Backup).")
        return redirect("accounts:backup")
    messages.success(request, f"Backup diunggah sebagai {tujuan.name}. Tekan Pulihkan pada baris itu untuk memakainya.")
    return redirect("accounts:backup")


@login_required
def backup_pulihkan(request, nama):
    """GET: confirmation for the modal. POST (with KATA_PULIHKAN typed): make
    a backup of the present state first, so the restore can be undone, then
    restore ``nama``."""
    _superuser(request)
    berkas = _berkas(nama)
    if request.method != "POST":
        return render(request, "accounts/_backup_pulihkan.html", {"nama": nama, "kata": KATA_PULIHKAN})
    if request.POST.get("konfirmasi", "").strip().upper() != KATA_PULIHKAN:
        messages.error(request, f"Pemulihan dibatalkan: ketik {KATA_PULIHKAN} untuk melanjutkan.")
        return redirect("accounts:backup")
    try:
        pengaman = buat("lengkap")
    except (OSError, sqlite3.Error) as galat:
        messages.error(request, f"Pemulihan dibatalkan: backup pengaman gagal dibuat ({galat}).")
        return redirect("accounts:backup")
    try:
        foto = pulihkan(berkas)
    except BackupTidakCocok as galat:
        messages.error(request, f"Pemulihan gagal: {galat} Data tidak berubah.")
    except Exception as galat:  # a dump that does not load: nothing was replaced (all or nothing)
        messages.error(
            request,
            f"Pemulihan gagal: {type(galat).__name__}: {str(galat)[:200]}. "
            f"Keadaan sebelum pemulihan tersimpan di {pengaman.name}.",
        )
    else:
        # The session table may have been replaced: write this one back.
        request.session.modified = True
        messages.success(
            request,
            f"Data dipulihkan dari {nama} ({foto} foto). Keadaan sebelumnya tersimpan di {pengaman.name}.",
        )
    return redirect("accounts:backup")
