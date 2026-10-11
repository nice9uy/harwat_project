import base64
import ipaddress
import os
import tempfile
from pathlib import Path

from django.conf import settings
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def generate_keypair():
    """Return (private_key_b64, public_key_b64) for a new WireGuard peer."""
    key = X25519PrivateKey.generate()
    priv = base64.b64encode(key.private_bytes_raw()).decode()
    pub = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    return priv, pub


def config_qr_img(config_text):
    """An ``<img>`` (inline PNG) of the QR code for a WireGuard config, with
    the Kemhan logo in its centre like the app's other QR codes."""
    from fleet.qr import qr_png_with_logo
    data = base64.b64encode(qr_png_with_logo(config_text)).decode()
    return f'<img src="data:image/png;base64,{data}" alt="QR config WireGuard" class="block w-full h-auto">'


def subnet():
    return ipaddress.ip_network(settings.VPN_SUBNET, strict=False)


def ip_server():
    """The server's address: the first host of the subnet."""
    return next(subnet().hosts())


def kapasitas():
    """How many peers the subnet holds (every host but the server's)."""
    return subnet().num_addresses - 3


def ip_bebas():
    """The lowest address of the subnet no peer has yet, as ``a.b.c.d/32``."""
    from .models import VpnPeer
    terpakai = {ip.split("/")[0] for ip in VpnPeer.objects.exclude(client_ip="").values_list("client_ip", flat=True)}
    hosts = subnet().hosts()
    next(hosts)  # the server's
    for ip in hosts:
        if str(ip) not in terpakai:
            return f"{ip}/32"
    raise ValueError(f"Subnet VPN {settings.VPN_SUBNET} penuh ({kapasitas()} peer).")


def server_conf():
    """The server's wg0.conf: its interface and one [Peer] per peer in the
    database that has a key. A switched-off account
    keeps its peer: it only can't log in to the app."""
    from .models import VpnPeer
    net = subnet()
    lines = [
        "[Interface]",
        f"Address = {ip_server()}/{net.prefixlen}",
        f"ListenPort = {settings.VPN_PORT}",
        f"PrivateKey = {settings.VPN_SERVER_PRIVKEY}",
        "PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth+ -j MASQUERADE",
        "PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth+ -j MASQUERADE",
    ]
    peers = VpnPeer.objects.exclude(public_key="").exclude(client_ip="").select_related("user").order_by("pk")
    for peer in peers:
        lines += ["", "[Peer]", f"# {peer.user.username}", f"PublicKey = {peer.public_key}"]
        if peer.preshared_key:
            lines.append(f"PresharedKey = {peer.preshared_key}")
        lines.append(f"AllowedIPs = {peer.client_ip.split('/')[0]}/32")
    return "\n".join(lines) + "\n"


def tulis_server_conf():
    """Write wg0.conf into VPN_CONF_DIR for the wireguard container, which
    applies it on change. Returns the path, or None when not configured."""
    if not (settings.VPN_CONF_DIR and settings.VPN_SERVER_PRIVKEY):
        return None
    folder = Path(settings.VPN_CONF_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed, so the container never reads half a file.
    fd, sementara = tempfile.mkstemp(dir=folder, prefix=".wg0-")
    with os.fdopen(fd, "w") as f:
        f.write(server_conf())
    os.chmod(sementara, 0o600)
    tujuan = folder / "wg0.conf"
    os.replace(sementara, tujuan)
    return tujuan
