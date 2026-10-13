#!/usr/bin/with-contenv bash
# Runs the WireGuard server from /vpn/wg0.conf, which the app rewrites
# whenever a peer is added, changed or removed. The file lives outside
# /config on purpose: the image hands everything under /config to its own
# user on start, and the app could then no longer write there.
# `wg syncconf` only touches the peers that differ, so the tunnels of
# everyone else stay up.
CONF=/vpn/wg0.conf
terakhir=""
nginx_terakhir=""

# VPN members open the app at the server's own VPN address (10.13.0.1:8000
# and :8443): from in here the host's address cannot be reached, nginx can.
# Its container address changes when it is recreated, so this is checked on
# every pass and the rules rewritten when it did. Without an "nginx" on the
# network (development) nothing is forwarded.
teruskan_ke_aplikasi() {
    local ip_nginx alamat_vpn port
    ip_nginx=$(getent hosts nginx | awk '{print $1; exit}')
    [ -n "$ip_nginx" ] || return 0
    [ "$ip_nginx" = "$nginx_terakhir" ] && return 0
    alamat_vpn=$(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
    [ -n "$alamat_vpn" ] || return 0
    iptables -t nat -N HARWAT 2>/dev/null || iptables -t nat -F HARWAT
    iptables -t nat -C PREROUTING -i wg0 -j HARWAT 2>/dev/null || iptables -t nat -A PREROUTING -i wg0 -j HARWAT
    for port in 8000 8443; do
        iptables -t nat -A HARWAT -d "$alamat_vpn" -p tcp --dport "$port" -j DNAT --to-destination "$ip_nginx:$port"
    done
    nginx_terakhir=$ip_nginx
    echo "sinkron: $alamat_vpn:8000 dan :8443 diteruskan ke aplikasi ($ip_nginx)"
}

while true; do
    sleep 5
    [ -f "$CONF" ] || continue
    [ -n "$terakhir" ] && teruskan_ke_aplikasi
    kini=$(stat -c '%Y-%s' "$CONF")
    [ "$kini" = "$terakhir" ] && continue
    # `wg syncconf` only changes peers: when the server's own address or
    # network changed (VPN_SUBNET), the interface has to come up afresh, or
    # peers outside the old network would connect and get no answer back.
    alamat_conf=$(awk -F'[ =]+' '/^Address/ {print $2; exit}' "$CONF")
    alamat_kini=$(ip -4 -o addr show wg0 2>/dev/null | awk '{print $4}')
    if [ -z "$terakhir" ] || [ "$alamat_conf" != "$alamat_kini" ]; then
        # First pass: drop a wg0 the image may have started from an old
        # config of its own, so address and key come from ours.
        wg-quick down wg0 >/dev/null 2>&1 || wg-quick down "$CONF" >/dev/null 2>&1
        ip link del wg0 >/dev/null 2>&1  # whatever is left of it
        wg-quick up "$CONF" && echo "sinkron: wg0 dinyalakan ($(wg show wg0 peers | wc -l) peer)"
        nginx_terakhir=""
        teruskan_ke_aplikasi
    else
        wg syncconf wg0 <(wg-quick strip "$CONF") && echo "sinkron: wg0 diperbarui ($(wg show wg0 peers | wc -l) peer)"
    fi
    terakhir=$kini
done
