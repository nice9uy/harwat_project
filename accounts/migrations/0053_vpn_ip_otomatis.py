import ipaddress

from django.conf import settings
from django.db import migrations, models


def isi_ip(apps, schema_editor):
    """Peers made before addresses were handed out automatically get the
    next free one of settings.VPN_SUBNET; so do peers sharing an address."""
    VpnPeer = apps.get_model("accounts", "VpnPeer")
    terpakai = set()
    tanpa = []
    for peer in VpnPeer.objects.order_by("pk"):
        if peer.client_ip and peer.client_ip not in terpakai:
            terpakai.add(peer.client_ip)
        else:
            tanpa.append(peer)
    hosts = ipaddress.ip_network(settings.VPN_SUBNET, strict=False).hosts()
    next(hosts)  # the server's
    for peer in tanpa:
        for ip in hosts:
            if f"{ip}/32" not in terpakai and str(ip) not in {t.split("/")[0] for t in terpakai}:
                peer.client_ip = f"{ip}/32"
                terpakai.add(peer.client_ip)
                peer.save(update_fields=["client_ip"])
                break
        else:
            raise RuntimeError(f"Subnet VPN {settings.VPN_SUBNET} penuh.")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0052_buku_jalan_opsional"),
    ]

    operations = [
        migrations.RunPython(isi_ip, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="vpnpeer",
            name="client_ip",
            field=models.CharField(blank=True, max_length=50, unique=True, verbose_name="IP Client (CIDR)"),
        ),
    ]
