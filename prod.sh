#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Whatever this script needs and the machine lacks is installed first:
# podman and podman-compose, curl (the Tailwind build), openssl (the secrets
# of .env.prod) and envsubst (Garage's config).
source scripts/pasang-komponen.sh
pasang_komponen podman podman-compose curl openssl envsubst
periksa_podman

# podman-compose 1.0.6 resolves relative paths in layered `-f` files against
# the directory of the FIRST `-f` file (podman/), not the caller's CWD. That's
# why --env-file below uses an absolute path instead of a bare filename, and
# why podman/compose.prod.yml's build context / env_file / volume paths use
# `..` (repo root) instead of `.`.

# Podman's collectstatic (and this compose's static asset serving) needs
# static/dist/output.css, a Tailwind build artifact that isn't in git. Rebuild
# it on every run, not only when it's missing: a copy left over from an older
# checkout lacks the classes newer templates use, and the app ships with
# those elements unstyled (collectstatic succeeds either way, so nothing else
# would catch it).
./scripts/build-css.sh

if [ ! -f .env.prod ]; then
    echo "Generating .env.prod (first run)..."
    umask 077
    TMP_ENV="$(mktemp .env.prod.XXXXXX)"
    {
        echo "DJANGO_DEBUG=False"
        echo "DJANGO_SECRET_KEY=$(openssl rand -hex 32)"
        # localhost plus this machine's name and addresses, so the app can be
        # opened by them straight away; add a domain or public address by hand.
        echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1$(printf ',%s' $(hostname 2>/dev/null) $(hostname -I 2>/dev/null))"
        echo "POSTGRES_DB=bmn_harwat"
        echo "POSTGRES_USER=bmn_harwat"
        echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
        echo "GARAGE_RPC_SECRET=$(openssl rand -hex 32)"
    } > "$TMP_ENV"
    # Atomic: only replaces .env.prod once the full write above succeeded, so
    # a missing openssl or an interrupted run never leaves a half-written file
    # that the `[ ! -f .env.prod ]` guard would then treat as valid forever.
    mv "$TMP_ENV" .env.prod
    echo ".env.prod created — back it up somewhere safe (it is gitignored)."
fi

# Settings added after .env.prod was first generated: appended once, so an
# existing .env.prod (and its secrets) is kept as it is.
tambah_env() {
    if ! grep -q "^$1=" .env.prod; then
        echo "$1=$2" >> .env.prod
        echo ".env.prod: $1 ditambahkan."
    fi
}
set -a
source .env.prod
set +a
# PostgreSQL: the app on the primary through PgBouncer, plus the role the two
# replicas stream with.
tambah_env DATABASE_ENGINE postgresql
# Valkey (compose.yml): the live badges' pub/sub between the app containers.
tambah_env REDIS_URL redis://valkey:6379/0
tambah_env DATABASE_URL "postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@pgbouncer:5432/${POSTGRES_DB}"
tambah_env REPLIKASI_USER replikator
tambah_env REPLIKASI_PASSWORD "$(openssl rand -hex 16)"
# Garage: the bucket of the uploaded photos and the key the app reads and
# writes it with (the same pair under the names Garage and the app each read).
tambah_env GARAGE_DEFAULT_BUCKET bmn-harwat
tambah_env GARAGE_DEFAULT_ACCESS_KEY "GK$(openssl rand -hex 12)"
tambah_env GARAGE_DEFAULT_SECRET_KEY "$(openssl rand -hex 32)"
set -a
source .env.prod
set +a
tambah_env GARAGE_ENDPOINT http://garage:3900
tambah_env GARAGE_BUCKET "${GARAGE_DEFAULT_BUCKET}"
tambah_env GARAGE_ACCESS_KEY "${GARAGE_DEFAULT_ACCESS_KEY}"
tambah_env GARAGE_SECRET_KEY "${GARAGE_DEFAULT_SECRET_KEY}"
# The SQLite file of the old setup (kept on its volume), and where backups go.
tambah_env SQLITE_LAMA /app/data/db.sqlite3
tambah_env BACKUP_DIR /app/backup
# The Server menu's container list: through the read-only relay (podman-api),
# never the Podman socket itself.
tambah_env PODMAN_API http://podman-api:2375
# Sizing, from this machine's cores and memory. Written once: to size again
# (after moving to another machine, or adding cores or memory) delete these
# lines from .env.prod and run this script again; edit them to tune by hand.
INTI=$(nproc)
RAM_MB=$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo)
antara() { local n=$1; [ "$n" -lt "$2" ] && n=$2; [ "$n" -gt "$3" ] && n=$3; echo "$n"; }
# App: about 1.5 worker processes per core over the three app containers.
tambah_env APP_PROSES "$(antara $(( (INTI * 3 / 2 + 2) / 3 )) 1 16)"
# PostgreSQL primary: a quarter of the memory as its own cache (at most 8 GB),
# half as what the system caches for it; parallel workers on half the cores.
tambah_env PG_SHARED_BUFFERS_MB "$(antara $(( RAM_MB / 4 )) 128 8192)"
tambah_env PG_EFFECTIVE_CACHE_MB "$(antara $(( RAM_MB / 2 )) 256 65536)"
tambah_env PG_WORK_MEM_MB "$(antara $(( RAM_MB / 2048 )) 4 32)"
tambah_env PG_MAINTENANCE_MB "$(antara $(( RAM_MB / 16 )) 64 1024)"
tambah_env PG_PARALEL "$(antara $(( INTI / 2 )) 1 8)"
tambah_env PG_REPLICA_BUFFERS_MB "$(antara $(( RAM_MB / 32 )) 128 1024)"
# PgBouncer: connections kept open to PostgreSQL, and app connections accepted.
tambah_env PGBOUNCER_POOL "$(antara $(( INTI * 10 )) 20 80)"
tambah_env PGBOUNCER_KLIEN 1000

# WireGuard: the server's key (the app derives the public one and writes
# wg0.conf into the volume shared with the wireguard container) and the
# network the peers get their addresses from, a /19: up to 8189 peers, so the
# 4096 members asked for fit (a /20 holds 4093).
tambah_env VPN_SERVER_PRIVKEY "$(openssl rand -base64 32)"
tambah_env VPN_CONF_DIR /vpn
tambah_env VPN_SUBNET 10.13.0.0/19
tambah_env VPN_PORT 51820
# VPN_AKTIF=0 switches the VPN off: no wireguard container, port 51820 closed.
# Peers and keys stay, so VPN_AKTIF=1 brings everyone's access back.
tambah_env VPN_AKTIF 1
if [ "$(grep "^VPN_AKTIF=" .env.prod | tail -1)" = "VPN_AKTIF=0" ]; then
    echo "VPN dinonaktifkan (VPN_AKTIF=0 di .env.prod)."
elif ! grep -q "^VPN_SERVER_ENDPOINT=." .env.prod; then
    echo "PERHATIAN: isi VPN_SERVER_ENDPOINT=<ip-publik>:51820 di .env.prod, tanpa itu config peer tidak bisa dipakai."
    echo "           (dari luar kantor: router harus meneruskan UDP 51820 ke mesin ini)"
fi
set -a
source .env.prod
set +a

KOMPOS=(podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml)

# Before the old containers are removed: the photos uploaded so far live
# inside them (/app/media was never on a volume), so copy them out. Once the
# photos are in Garage there is nothing left in there and this copies nothing.
mkdir -p migrasi/media
for nama in podman_app1_1 podman_app2_1 podman_app3_1; do
    if podman container exists "$nama" && podman exec "$nama" test -d /app/media 2>/dev/null; then
        podman cp "$nama:/app/media/." migrasi/media/ 2>/dev/null \
            && echo "Foto dari $nama disalin ke migrasi/media/." || true
    fi
done

# umask 077 also covers this regeneration (podman/garage.prod.toml is
# rewritten on every run, not just first-run) — re-set here so a run where
# .env.prod already existed (skipping the block above) still creates
# garage.prod.toml 0600 instead of the default 0644.
umask 077
envsubst '${GARAGE_RPC_SECRET}' < podman/garage.toml.template > podman/garage.prod.toml

# The HTTPS certificate nginx serves on port 8443 (mkcert; made again only
# when this machine's names or addresses changed or it nears its end). Members
# on the VPN open the app at the server's VPN address (the first of
# VPN_SUBNET), so that is named in the certificate too; TLS_NAMA in .env.prod
# adds more, separated by commas: a public address, a domain.
./scripts/perbarui-tls.sh

# ...and kept up to date while the stack runs: scripts/perbarui-tls.sh every
# day at 00:00 WIB (a new certificate once the old one is within 30 days of
# its end, nginx reloaded without stopping), through a systemd user timer,
# else cron. Best effort.
FOLDER_PROYEK="$(pwd)"
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT_DIR/harwat-tls.service" <<UNIT
[Unit]
Description=Harwat: perbarui sertifikat HTTPS bila hampir habis

[Service]
Type=oneshot
WorkingDirectory=${FOLDER_PROYEK}
ExecStart=${FOLDER_PROYEK}/scripts/perbarui-tls.sh
UNIT
    cat > "$UNIT_DIR/harwat-tls.timer" <<UNIT
[Unit]
Description=Harwat: cek sertifikat HTTPS setiap hari pukul 00:00 WIB

[Timer]
OnCalendar=*-*-* 00:00:00 Asia/Jakarta
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
UNIT
    systemctl --user daemon-reload
    systemctl --user enable --now harwat-tls.timer >/dev/null 2>&1 \
        && echo "Timer harwat-tls aktif: sertifikat HTTPS dicek setiap hari pukul 00:00 WIB." \
        || echo "PERHATIAN: timer harwat-tls tidak bisa diaktifkan."
elif command -v crontab >/dev/null 2>&1; then
    # cron runs on the server's own clock: 00:00 there (WIB when the server's
    # timezone is Asia/Jakarta, as `timedatectl` shows).
    BARIS="0 0 * * * cd ${FOLDER_PROYEK} && ./scripts/perbarui-tls.sh >> ${FOLDER_PROYEK}/podman/tls/perbarui.log 2>&1"
    ( crontab -l 2>/dev/null | grep -v 'scripts/perbarui-tls.sh'; echo "$BARIS" ) | crontab - \
        && echo "Cron perbarui-tls aktif: sertifikat HTTPS dicek setiap hari pukul 00:00 (jam server)."
else
    echo "PERHATIAN: tidak ada systemd/cron; sertifikat HTTPS hanya diperbarui saat prod.sh dijalankan."
fi

# Rootless containers stop when their user logs out and do not come back
# after a reboot unless the user "lingers" and podman's restart service is
# on. Best effort (lingering may need the administrator): without it the
# stack has to be started again by hand after a reboot.
if command -v loginctl >/dev/null 2>&1; then
    if [ "$(loginctl show-user "$(id -un)" -p Linger 2>/dev/null)" != "Linger=yes" ]; then
        loginctl enable-linger "$(id -un)" >/dev/null 2>&1 \
            && echo "Linger diaktifkan: kontainer tetap hidup setelah logout." \
            || echo "PERHATIAN: linger belum aktif — jalankan 'sudo loginctl enable-linger $(id -un)' agar kontainer tetap hidup setelah logout/reboot."
    fi
    systemctl --user enable podman-restart.service >/dev/null 2>&1 || true
fi

# The Podman API socket the podman-api relay reads the container list from
# (best effort: without it only the Server menu's list stays empty).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if command -v systemctl >/dev/null 2>&1 && ! systemctl --user is-active --quiet podman.socket 2>/dev/null; then
    systemctl --user enable --now podman.socket >/dev/null 2>&1 \
        && echo "podman.socket diaktifkan (untuk menu Server)." \
        || echo "podman.socket tidak bisa diaktifkan — daftar kontainer di menu Server akan kosong."
fi

# The host ports nginx is published on (PORT_HTTP / PORT_HTTPS in .env.prod,
# 8000 and 8443 by default). Below 1024 (80 and 443, so that the address needs
# no port) the host has to let ordinary users open them: rootless Podman runs
# as this user. Stop here with the fix rather than fail halfway through `up`.
PORT_HTTP="${PORT_HTTP:-8000}"
PORT_HTTPS="${PORT_HTTPS:-8443}"
AWAL_BEBAS=$(cat /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || echo 1024)
for PORT in "$PORT_HTTP" "$PORT_HTTPS"; do
    if [ "$PORT" -lt "$AWAL_BEBAS" ]; then
        echo "Port $PORT belum boleh dibuka oleh pengguna biasa (mulai dari $AWAL_BEBAS). Jalankan sekali:" >&2
        echo "  echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee /etc/sysctl.d/99-harwat-port.conf && sudo sysctl --system" >&2
        exit 1
    fi
done
alamat_port() {  # "http" 80 -> "", "https" 8443 -> ":8443"
    if { [ "$1" = http ] && [ "$2" = 80 ]; } || { [ "$1" = https ] && [ "$2" = 443 ]; }; then echo ""; else echo ":$2"; fi
}
HTTP_PORT_TEKS="$(alamat_port http "$PORT_HTTP")"
HTTPS_PORT_TEKS="$(alamat_port https "$PORT_HTTPS")"

# A stack that is still running is stopped first, then started again — same
# reasoning as dev.sh: dev and prod share service names
# (postgres/valkey/garage/pgbouncer) from the base compose.yml, so a leftover
# dev run would otherwise get reused as-is by `up` instead of recreated
# against this run's config. --remove-orphans also clears the dev-only `app`
# container. Only this stack's containers are touched (podman-compose names
# the project after the first -f file's directory); the volumes, and so the
# database, the photos and the backups, stay.
PROYEK=podman
BERJALAN="$(podman ps --filter "label=io.podman.compose.project=${PROYEK}" --format '{{.Names}}' | tr '\n' ' ')"
if [ -n "${BERJALAN// /}" ]; then
    echo "Kontainer yang sedang berjalan dimatikan dulu: ${BERJALAN}"
else
    echo "Tidak ada kontainer yang sedang berjalan."
fi
"${KOMPOS[@]}" down --remove-orphans
# What `down` left behind (a container from an older compose file it no
# longer knows, or one stuck stopping) would still hold its name and port.
SISA="$(podman ps -a --filter "label=io.podman.compose.project=${PROYEK}" --format '{{.Names}}' | tr '\n' ' ')"
if [ -n "${SISA// /}" ]; then
    echo "Menghapus kontainer yang tersisa: ${SISA}"
    # shellcheck disable=SC2086
    podman rm -f ${SISA} >/dev/null
fi

echo "Membangun image dan menjalankan ulang..."
"${KOMPOS[@]}" up -d --build
# Switched off: the wireguard container is taken away again (it is part of
# the compose file, so `up` makes it), which also closes its port.
if [ "${VPN_AKTIF:-1}" = "0" ] && podman container exists "${PROYEK}_wireguard_1"; then
    podman rm -f "${PROYEK}_wireguard_1" >/dev/null
    echo "Kontainer WireGuard tidak dijalankan (VPN_AKTIF=0)."
fi

# Idempotent — safe to run on every invocation, not just first-run. Nothing
# else in this stack ever runs migrations, and db.sqlite3 is schemaless on a
# fresh volume, so skipping this would leave every table missing.
# The primary may have been created before replication existed (its init
# script only runs on an empty data directory): make sure the role the
# replicas use is there, with the current password. Safe to repeat.
# A container that could not be made (an image that would not pull, a port
# already taken) must stop the run here, not leave it waiting for good.
if ! podman container exists "${PROYEK}_postgres_1" || ! podman container exists "${PROYEK}_app1_1"; then
    echo "Kontainer tidak terbentuk semua — lihat galat 'podman run' di atas. Yang ada:" >&2
    podman ps -a --filter "label=io.podman.compose.project=${PROYEK}" --format '  {{.Names}}  {{.Status}}' >&2
    exit 1
fi
echo "Menunggu PostgreSQL primary..."
TUNGGU=0
until "${KOMPOS[@]}" exec -T postgres pg_isready -q -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"; do
    TUNGGU=$((TUNGGU + 2))
    if [ "$TUNGGU" -ge 180 ]; then
        echo "PostgreSQL belum siap setelah 3 menit — lihat 'podman logs ${PROYEK}_postgres_1'." >&2
        exit 1
    fi
    sleep 2
done
# (Passed with -c: the role name and password are generated here, hex only.)
"${KOMPOS[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -q -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${REPLIKASI_USER}') THEN CREATE ROLE \"${REPLIKASI_USER}\" WITH REPLICATION LOGIN; END IF; END \$\$;" \
    -c "ALTER ROLE \"${REPLIKASI_USER}\" WITH REPLICATION LOGIN PASSWORD '${REPLIKASI_PASSWORD}';"

# Right after `up` the containers' names may not resolve yet (the network's
# DNS starts a moment later): migrating then fails with "failed to resolve
# host 'pgbouncer'". Wait until the app reaches the database.
TUNGGU=0
until "${KOMPOS[@]}" exec -T app1 python -c "import socket; socket.create_connection(('pgbouncer', 5432), 3).close()" 2>/dev/null; do
    TUNGGU=$((TUNGGU + 2))
    if [ "$TUNGGU" -ge 120 ]; then
        echo "Aplikasi belum bisa menjangkau pgbouncer setelah 2 menit — lihat 'podman logs ${PROYEK}_pgbouncer_1'." >&2
        exit 1
    fi
    sleep 2
done
"${KOMPOS[@]}" exec -T app1 python manage.py migrate --noinput
# The WireGuard server's config, from the peers now in the database. The
# volume it is written to belongs to whichever container mounted it first:
# when that was the wireguard one it is root's, and the app (user "app")
# could not write there.
podman exec -u 0 "${PROYEK}_app1_1" chown app:app /vpn
"${KOMPOS[@]}" exec -T app1 python manage.py vpn_server_conf
# Kodam, Korem, Kodim and Koramil for Pengaturan > Satuan; skips what is there.
"${KOMPOS[@]}" exec -T app1 python manage.py impor_satuan

# One-time moves from the old setup; each does nothing once it has been done.
# The data: from the SQLite file into PostgreSQL (only into an empty database).
"${KOMPOS[@]}" exec -T app1 sh -c 'if [ -f "$SQLITE_LAMA" ]; then python manage.py impor_sqlite; fi'
# The photos: from the folder rescued above into Garage (existing ones are skipped).
"${KOMPOS[@]}" exec -T app1 python manage.py impor_media /app/migrasi-media
# Vehicle statuses follow the inspections and repairs.
"${KOMPOS[@]}" exec -T app1 python manage.py hitung_status_kendaraan

echo "Replica yang tersambung ke primary (seharusnya 2 baris 'streaming'):"
"${KOMPOS[@]}" exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Atc \
    "select application_name, client_addr, state from pg_stat_replication" || true

echo
echo "Kontainer yang berjalan:"
podman ps --filter "label=io.podman.compose.project=${PROYEK}" --format '  {{.Names}}  {{.Status}}'
ALAMAT_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "Selesai. Aplikasi: http://localhost${HTTP_PORT_TEKS}${ALAMAT_IP:+ | http://$ALAMAT_IP${HTTP_PORT_TEKS}}"
echo "         HTTPS:    https://localhost${HTTPS_PORT_TEKS}${ALAMAT_IP:+ | https://$ALAMAT_IP${HTTPS_PORT_TEKS}}"
[ "${VPN_AKTIF:-1}" = "0" ] || echo "         Lewat VPN: https://${ALAMAT_VPN}:8443"
echo "         (impor podman/tls/rootCA.pem di browser agar HTTPS tanpa peringatan; unduh: http://${ALAMAT_IP:-localhost}${HTTP_PORT_TEKS}/rootCA.pem)"
