"""Lifts a block from the server's shell, for when a superuser blocked
themselves out (Hacking Activity's blacklist, accounts.keamanan).

    python manage.py buka_blokir_ip 203.0.113.7
    python manage.py buka_blokir_ip --semua
"""
from django.core.management.base import BaseCommand, CommandError

from accounts import keamanan
from accounts.models import IpBlokir


class Command(BaseCommand):
    help = "Buka blokir IP (Hacking Activity)."

    def add_arguments(self, parser):
        parser.add_argument("alamat", nargs="?", help="IP atau rentang CIDR yang diblokir")
        parser.add_argument("--semua", action="store_true", help="buka semua blokir")

    def handle(self, alamat=None, semua=False, **options):
        if semua:
            qs = IpBlokir.objects.all()
        elif alamat:
            qs = IpBlokir.objects.filter(alamat=keamanan.alamat_sah(alamat) or alamat)
        else:
            raise CommandError("Sebutkan alamatnya, atau --semua.")
        jumlah = qs.count()
        qs.delete()
        keamanan.segarkan_blokir()
        self.stdout.write(f"{jumlah} blokir dibuka.")
