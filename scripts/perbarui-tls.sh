#!/usr/bin/env bash
# Keeps the HTTPS certificate nginx serves up to date while the stack runs:
# scripts/siapkan-tls.sh makes a new one (signed by the same authority, so no
# device has to import anything again) when it is within 30 days of expiring or
# the server's names/addresses changed, and nginx then reloads it without
# stopping. Run by prod.sh at start and, through the harwat-tls timer (or cron)
# that prod.sh installs, every day at 00:00 WIB.
#
#     ./scripts/perbarui-tls.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# The names prod.sh puts in the certificate: TLS_NAMA from .env.prod plus the
# server's VPN address (the first of VPN_SUBNET).
TLS_NAMA_ENV=""
VPN_SUBNET_ENV="10.13.0.0/19"
if [ -f .env.prod ]; then
    TLS_NAMA_ENV="$(grep -E '^TLS_NAMA=' .env.prod | tail -n1 | cut -d= -f2- || true)"
    VPN_SUBNET_ENV="$(grep -E '^VPN_SUBNET=' .env.prod | tail -n1 | cut -d= -f2- || true)"
    VPN_SUBNET_ENV="${VPN_SUBNET_ENV:-10.13.0.0/19}"
fi
ALAMAT_VPN="${VPN_SUBNET_ENV%%/*}"
ALAMAT_VPN="${ALAMAT_VPN%.*}.$(( ${ALAMAT_VPN##*.} + 1 ))"

SEBELUM="$(sha256sum podman/tls/cert.pem 2>/dev/null | cut -d' ' -f1 || true)"
TLS_NAMA="${TLS_NAMA_ENV} ${ALAMAT_VPN}" ./scripts/siapkan-tls.sh
SESUDAH="$(sha256sum podman/tls/cert.pem 2>/dev/null | cut -d' ' -f1 || true)"

if [ "$SEBELUM" != "$SESUDAH" ]; then
    NGINX="$(podman ps --filter label=io.podman.compose.service=nginx --format '{{.Names}}' 2>/dev/null | head -n1 || true)"
    if [ -n "$NGINX" ]; then
        podman exec "$NGINX" nginx -s reload && echo "Sertifikat HTTPS diperbarui; nginx ($NGINX) memuat yang baru."
    else
        echo "Sertifikat HTTPS diperbarui; nginx belum jalan, dipakai saat start berikutnya."
    fi
fi
echo "Sertifikat HTTPS berlaku sampai: $(openssl x509 -enddate -noout -in podman/tls/cert.pem | cut -d= -f2)"
