from django.core.management.base import BaseCommand

from accounts.models import VpnPeer
from accounts.vpn_utils import kapasitas, tulis_server_conf


class Command(BaseCommand):
    help = "Tulis ulang wg0.conf server WireGuard dari peer di database"

    def handle(self, *args, **options):
        tujuan = tulis_server_conf()
        if tujuan is None:
            self.stdout.write("VPN_CONF_DIR / VPN_SERVER_PRIVKEY belum diset, tidak ada yang ditulis.")
            return
        self.stdout.write(f"{tujuan}: {VpnPeer.objects.count()} peer dari kapasitas {kapasitas()}.")
