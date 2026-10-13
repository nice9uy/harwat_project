#!/usr/bin/env bash
# Redeploys production with the latest code: backs the database up, updates
# the code, runs ./prod.sh and checks that the app answers.
#
#   On the server:
#     ./redeploy.sh                  # git pull from origin, then redeploy
#     ./redeploy.sh --tanpa-pull     # redeploy the code that is already here
#
#   From a development machine (sends this machine's commits to the server
#   over SSH, so it works even before they are pushed to GitHub):
#     ./redeploy.sh nice9uy@10.10.157.147
#     ./redeploy.sh nice9uy@10.10.157.147 /home/nice9uy/Documents/harwat_project
#
# The data (database, photos, backups, VPN keys) lives on volumes and in
# .env.prod and is kept: only the containers are replaced.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

FOLDER_SERVER_BAWAAN='~/Documents/harwat_project'

# --- from a development machine: hand over to the server ---------------------
if [ "${1:-}" != "" ] && [ "${1#--}" = "$1" ]; then
    SERVER="$1"
    FOLDER="${2:-$FOLDER_SERVER_BAWAAN}"
    if [ -n "$(git status --porcelain)" ]; then
        echo "PERHATIAN: ada perubahan yang belum di-commit; yang dikirim hanya yang sudah di-commit."
    fi
    CABANG="$(git rev-parse --abbrev-ref HEAD)"
    # One SSH connection for every step below: the password is asked once.
    KONTROL="$(mktemp -u "${TMPDIR:-/tmp}/redeploy-ssh-XXXXXX")"
    SSH=(ssh -o ControlMaster=auto -o ControlPath="$KONTROL" -o ControlPersist=120 -o ConnectTimeout=10)
    selesai() { ssh -o ControlPath="$KONTROL" -O exit "$SERVER" >/dev/null 2>&1 || true; }
    trap selesai EXIT

    echo "== Menyambung ke $SERVER"
    DI_SERVER="$("${SSH[@]}" "$SERVER" "git -C $FOLDER rev-parse HEAD")"
    DI_SINI="$(git rev-parse HEAD)"
    if [ "$DI_SERVER" = "$DI_SINI" ]; then
        echo "Kode di server sudah sama dengan di sini ($(git rev-parse --short HEAD))."
    elif git cat-file -e "${DI_SERVER}^{commit}" 2>/dev/null && git merge-base --is-ancestor "$DI_SERVER" "$DI_SINI"; then
        echo "== Mengirim $(git rev-list --count "${DI_SERVER}..${DI_SINI}") commit ke server"
        git log --oneline "${DI_SERVER}..${DI_SINI}" | sed 's/^/   /'
        BUNDEL="$(mktemp "${TMPDIR:-/tmp}/harwat-XXXXXX.bundle")"
        git bundle create "$BUNDEL" "${DI_SERVER}..${CABANG}" >/dev/null 2>&1
        scp -q -o ControlPath="$KONTROL" "$BUNDEL" "$SERVER:/tmp/harwat-redeploy.bundle"
        rm -f "$BUNDEL"
        "${SSH[@]}" "$SERVER" "cd $FOLDER && git pull -q --ff-only /tmp/harwat-redeploy.bundle $CABANG && rm -f /tmp/harwat-redeploy.bundle"
    else
        echo "Kode di server ($DI_SERVER) bukan pendahulu kode di sini: server punya commit yang tidak ada di mesin ini." >&2
        echo "Samakan dulu (git pull di sini, atau periksa server), lalu ulangi." >&2
        exit 1
    fi
    echo "== Menjalankan redeploy di server"
    "${SSH[@]}" -t "$SERVER" "cd $FOLDER && ./redeploy.sh --tanpa-pull"
    exit $?
fi

# --- on the server -----------------------------------------------------------
PROYEK=podman
MULAI=$(date +%s)

if [ "${1:-}" != "--tanpa-pull" ]; then
    echo "== Mengambil kode terbaru"
    SEBELUM="$(git rev-parse HEAD)"
    git pull --ff-only
    if [ "$SEBELUM" = "$(git rev-parse HEAD)" ]; then
        echo "Tidak ada commit baru; tetap dijalankan ulang."
    else
        git log --oneline "${SEBELUM}..HEAD" | sed 's/^/   /'
    fi
fi
echo "Versi yang dipasang: $(git log --oneline -1)"

# A copy of the database before anything is replaced, in the backup volume
# (menu Backup lists it). Skipped when the app isn't running yet.
if podman container exists "${PROYEK}_app1_1" && [ "$(podman inspect -f '{{.State.Running}}' "${PROYEK}_app1_1" 2>/dev/null)" = "true" ]; then
    echo "== Mencadangkan database"
    podman exec "${PROYEK}_app1_1" python manage.py shell -c \
        "from accounts import backup; print('Backup:', backup.buat('database').name)" 2>/dev/null | tail -1 \
        || echo "PERHATIAN: backup gagal dibuat; redeploy tetap dilanjutkan."
else
    echo "Aplikasi belum berjalan: tidak ada yang dicadangkan."
fi

echo "== Menjalankan ./prod.sh"
./prod.sh

echo "== Memeriksa aplikasi"
SIAP=""
for _ in $(seq 1 30); do
    KODE="$(curl -sk -m 5 -o /dev/null -w '%{http_code}' https://localhost:8443/login/ || true)"
    if [ "$KODE" = "200" ]; then
        SIAP=1
        break
    fi
    sleep 2
done
if [ -z "$SIAP" ]; then
    echo "Aplikasi belum menjawab di https://localhost:8443/login/ (kode terakhir: ${KODE:-tidak ada})." >&2
    echo "Periksa: podman ps -a ; podman logs ${PROYEK}_nginx_1 ; podman logs ${PROYEK}_app1_1" >&2
    exit 1
fi
MATI="$(podman ps -a --filter "label=io.podman.compose.project=${PROYEK}" --filter status=exited --format '{{.Names}}' | grep -v 'static-sync' || true)"
if [ -n "$MATI" ]; then
    echo "PERHATIAN: kontainer ini tidak berjalan: $MATI" >&2
fi
echo "Redeploy selesai dalam $(( $(date +%s) - MULAI )) detik. Aplikasi menjawab (200) — versi $(git rev-parse --short HEAD)."
