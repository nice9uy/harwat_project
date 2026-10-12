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
# static/dist/output.css, a Tailwind build artifact that isn't in git. Build
# it automatically if it's missing so a fresh checkout doesn't silently ship
# a visually broken app (collectstatic succeeds either way — it doesn't fail
# loudly if this file is absent, so the guard has to happen here instead).
if [ ! -f static/dist/output.css ]; then
    ./scripts/build-css.sh
fi

if [ ! -f .env.prod ]; then
    echo "Generating .env.prod (first run)..."
    umask 077
    TMP_ENV="$(mktemp .env.prod.XXXXXX)"
    {
        echo "DJANGO_DEBUG=False"
        echo "DJANGO_SECRET_KEY=$(openssl rand -hex 32)"
        echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1"
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
# WireGuard: the server's key (the app derives the public one and writes
# wg0.conf into the volume shared with the wireguard container) and the
# network the peers get their addresses from, a /20 for up to 4093 peers.
tambah_env VPN_SERVER_PRIVKEY "$(openssl rand -base64 32)"
tambah_env VPN_CONF_DIR /vpn
tambah_env VPN_SUBNET 10.13.0.0/20
tambah_env VPN_PORT 51820
if ! grep -q "^VPN_SERVER_ENDPOINT=." .env.prod; then
    echo "PERHATIAN: isi VPN_SERVER_ENDPOINT=<ip-publik>:51820 di .env.prod, tanpa itu config peer tidak bisa dipakai."
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
# when this machine's names or addresses changed).
./scripts/siapkan-tls.sh

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
echo "Selesai. Aplikasi: http://localhost:8000${ALAMAT_IP:+ | http://$ALAMAT_IP:8000}"
echo "         HTTPS:    https://localhost:8443${ALAMAT_IP:+ | https://$ALAMAT_IP:8443}"
echo "         (impor podman/tls/rootCA.pem di browser agar HTTPS tanpa peringatan; unduh: http://${ALAMAT_IP:-localhost}:8000/rootCA.pem)"
