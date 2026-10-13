#!/usr/bin/env bash
# The HTTPS certificate nginx serves in production, made with mkcert: a local
# certificate authority (kept in podman/tls/ca) signs a certificate for this
# machine's names and addresses. A browser trusts it once that authority's
# certificate (podman/tls/rootCA.pem, also offered at /rootCA.pem) has been
# imported there; until then it warns, but the connection is encrypted.
#
#     ./scripts/siapkan-tls.sh                    # localhost + this machine's addresses
#     TLS_NAMA="harwat.lan,203.0.113.7" ./scripts/siapkan-tls.sh   # plus these
#
# (separated by commas or spaces; in .env.prod use commas, a line with a space
# in it is not a valid setting there)
#
# Run by prod.sh on every start: the certificate is made again only when the
# list of names changed or it is close to expiring. mkcert is downloaded to
# bin/ when it isn't installed (no root needed); without it (no internet) a
# self-signed certificate from openssl is used so that nginx still starts.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

MKCERT_VERSI="v1.4.4"
DIR="podman/tls"
umask 077
mkdir -p "$DIR/ca"

# Every name the site is opened by: localhost, the host name, each address.
NAMA="localhost 127.0.0.1 ::1 $(hostname 2>/dev/null || true) $(hostname -I 2>/dev/null || true) $(echo "${TLS_NAMA:-}" | tr ',' ' ')"
NAMA="$(echo $NAMA | tr ' ' '\n' | grep -v '^$' | sort -u | tr '\n' ' ')"

masih_berlaku() {
    # Valid for at least 30 more days.
    [ -f "$DIR/cert.pem" ] && [ -f "$DIR/key.pem" ] && openssl x509 -checkend 2592000 -noout -in "$DIR/cert.pem" >/dev/null 2>&1
}

if masih_berlaku && [ "$(cat "$DIR/nama.txt" 2>/dev/null)" = "$NAMA" ]; then
    echo "Sertifikat HTTPS sudah ada untuk: $NAMA"
    exit 0
fi

MKCERT="$(command -v mkcert || true)"
if [ -z "$MKCERT" ]; then
    MKCERT="bin/mkcert"
    if [ ! -x "$MKCERT" ]; then
        case "$(uname -m)" in
            aarch64|arm64) ARSITEKTUR="arm64" ;;
            x86_64) ARSITEKTUR="amd64" ;;
            *) ARSITEKTUR="" ;;
        esac
        if [ -n "$ARSITEKTUR" ]; then
            mkdir -p bin
            echo "Mengunduh mkcert ${MKCERT_VERSI}..."
            if curl -fsSL -o "$MKCERT" \
                "https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSI}/mkcert-${MKCERT_VERSI}-linux-${ARSITEKTUR}"; then
                chmod +x "$MKCERT"
            else
                rm -f "$MKCERT"
            fi
        fi
    fi
fi

if [ -x "$MKCERT" ]; then
    # The authority lives in the project (gitignored), not in the home
    # directory, so the same one signs every later certificate.
    # shellcheck disable=SC2086
    CAROOT="$(pwd)/$DIR/ca" "$MKCERT" -cert-file "$DIR/cert.pem" -key-file "$DIR/key.pem" $NAMA
    cp "$DIR/ca/rootCA.pem" "$DIR/rootCA.pem"
    echo "Sertifikat HTTPS (mkcert) dibuat untuk: $NAMA"
    echo "Agar browser tidak memberi peringatan, impor $DIR/rootCA.pem (juga di https://<alamat>:8443/rootCA.pem) sebagai otoritas tepercaya."
else
    echo "mkcert tidak tersedia — memakai sertifikat self-signed (browser akan memberi peringatan)." >&2
    SAN=""
    for n in $NAMA; do
        case "$n" in
            *:*|*[!0-9.]*) [ "${n#*:}" != "$n" ] && SAN="$SAN,IP:$n" || SAN="$SAN,DNS:$n" ;;
            *) SAN="$SAN,IP:$n" ;;
        esac
    done
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=Harwat" \
        -addext "subjectAltName=${SAN#,}" -keyout "$DIR/key.pem" -out "$DIR/cert.pem" >/dev/null 2>&1
    cp "$DIR/cert.pem" "$DIR/rootCA.pem"
fi
echo "$NAMA" > "$DIR/nama.txt"
# nginx's master process (root inside its container, this user outside) loads
# the key; its workers (another user) only hand out the two certificates.
chmod 600 "$DIR/key.pem"
chmod 644 "$DIR/cert.pem" "$DIR/rootCA.pem"
chmod 755 "$DIR"
chmod 700 "$DIR/ca"
