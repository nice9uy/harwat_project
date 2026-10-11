from pathlib import Path

from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Copy a folder of uploaded photos (an old media/ directory) into the current storage "
        "(the Garage bucket in production), keeping each file's path. Files already there are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument("folder")

    def handle(self, *args, **options):
        folder = Path(options["folder"])
        if not folder.is_dir():
            raise CommandError(f"{folder} bukan folder.")
        disalin = dilewati = 0
        for berkas in sorted(folder.rglob("*")):
            if not berkas.is_file():
                continue
            nama = berkas.relative_to(folder).as_posix()
            if default_storage.exists(nama):
                dilewati += 1
                continue
            with berkas.open("rb") as f:
                tersimpan = default_storage.save(nama, File(f))
            if tersimpan != nama:
                # The database points at the original name: don't leave a renamed copy behind.
                default_storage.delete(tersimpan)
                raise CommandError(f"{nama} tersimpan sebagai {tersimpan}; nama tidak boleh berubah.")
            disalin += 1
        self.stdout.write(self.style.SUCCESS(f"{disalin} file disalin, {dilewati} sudah ada."))
