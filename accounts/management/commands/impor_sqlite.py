import tempfile

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

# Rebuilt by migrate in the new database (with ids of its own), or not worth carrying over.
TIDAK_DIBAWA = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


class Command(BaseCommand):
    help = (
        "Copy everything from the SQLite file production used to run on (settings.SQLITE_LAMA, "
        "database alias 'lama') into the current database. Refuses when the current database "
        "already has users, so it only ever fills an empty one."
    )

    def handle(self, *args, **options):
        if "lama" not in settings.DATABASES:
            raise CommandError("Tidak ada database lama: set SQLITE_LAMA ke file SQLite-nya (dan DATABASE_URL).")
        if User.objects.exists():
            self.stdout.write("Database sekarang sudah berisi user; tidak ada yang diimpor.")
            return
        # Bring the old file up to the current tables first, so it can be read with today's models.
        call_command("migrate", database="lama", interactive=False, verbosity=0)
        if not User.objects.using("lama").exists():
            self.stdout.write("Database lama kosong; tidak ada yang diimpor.")
            return
        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8") as f:
            call_command("dumpdata", database="lama", exclude=TIDAK_DIBAWA, stdout=f, verbosity=0)
            f.flush()
            # The rows migrate made here (role groups, KM rows) come over from the old file instead.
            call_command("flush", interactive=False, verbosity=0)
            call_command("loaddata", f.name, verbosity=0)
        self.stdout.write(self.style.SUCCESS(
            f"Impor selesai: {User.objects.count()} user dari {settings.SQLITE_LAMA}."
        ))
