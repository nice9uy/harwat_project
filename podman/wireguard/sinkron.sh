#!/usr/bin/with-contenv bash
# Runs the WireGuard server from /vpn/wg0.conf, which the app rewrites
# whenever a peer is added, changed or removed. The file lives outside
# /config on purpose: the image hands everything under /config to its own
# user on start, and the app could then no longer write there.
# `wg syncconf` only touches the peers that differ, so the tunnels of
# everyone else stay up.
CONF=/vpn/wg0.conf
terakhir=""
while true; do
    sleep 5
    [ -f "$CONF" ] || continue
    kini=$(stat -c '%Y-%s' "$CONF")
    [ "$kini" = "$terakhir" ] && continue
    if [ -z "$terakhir" ]; then
        # First pass: drop a wg0 the image may have started from an old
        # config of its own, so address and key come from ours.
        wg-quick down wg0 >/dev/null 2>&1
        wg-quick up "$CONF" && echo "sinkron: wg0 dinyalakan ($(wg show wg0 peers | wc -l) peer)"
    else
        wg syncconf wg0 <(wg-quick strip "$CONF") && echo "sinkron: wg0 diperbarui ($(wg show wg0 peers | wc -l) peer)"
    fi
    terakhir=$kini
done
