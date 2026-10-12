#!/usr/bin/env bash
# Installs what dev.sh and prod.sh need when it is missing, with the host's
# package manager (apt, dnf, yum, zypper, pacman or apk; through sudo unless
# already root). Sourced by both scripts:
#
#     source scripts/pasang-komponen.sh
#     pasang_komponen podman podman-compose curl openssl envsubst
#
# A component already on the PATH is left alone, so a machine that has
# everything pays nothing. PASANG_SIMULASI=1 prints the install commands
# instead of running them.

# Command -> package, per package manager (the same name unless listed).
_paket() {
    local perintah="$1" pengelola="$2"
    case "$perintah:$pengelola" in
        envsubst:apt-get) echo gettext-base ;;
        envsubst:*) echo gettext ;;
        awk:apt-get|awk:dnf|awk:yum|awk:zypper|awk:pacman) echo gawk ;;
        hostname:pacman) echo inetutils ;;
        hostname:apk) echo net-tools ;;
        *) echo "$perintah" ;;
    esac
}

# What rootless podman needs beside itself (user namespaces, networking,
# storage); the names differ per distribution and some are already pulled in.
_paket_pendamping_podman() {
    case "$1" in
        apt-get) echo "uidmap slirp4netns fuse-overlayfs" ;;
        dnf|yum) echo "shadow-utils slirp4netns fuse-overlayfs" ;;
        zypper) echo "shadow slirp4netns fuse-overlayfs" ;;
        pacman) echo "slirp4netns fuse-overlayfs" ;;
        apk) echo "shadow-uidmap slirp4netns fuse-overlayfs" ;;
    esac
}

_pengelola_paket() {
    local p
    for p in apt-get dnf yum zypper pacman apk; do
        if command -v "$p" >/dev/null 2>&1; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

_jalankan() {
    if [ "${PASANG_SIMULASI:-}" = "1" ]; then
        echo "[simulasi] $*"
        return 0
    fi
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "Perlu hak root untuk: $* — jalankan sebagai root atau pasang sudo." >&2
        return 1
    fi
}

_pasang_paket() {
    local pengelola="$1"
    shift
    case "$pengelola" in
        apt-get)
            # Once per run: the package lists of a fresh machine are empty.
            if [ -z "${_APT_DIPERBARUI:-}" ]; then
                _jalankan env DEBIAN_FRONTEND=noninteractive apt-get update -y || true
                _APT_DIPERBARUI=1
            fi
            _jalankan env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
            ;;
        dnf|yum) _jalankan "$pengelola" install -y "$@" ;;
        zypper) _jalankan zypper --non-interactive install "$@" ;;
        pacman) _jalankan pacman -Sy --noconfirm --needed "$@" ;;
        apk) _jalankan apk add "$@" ;;
    esac
}

# podman-compose is not packaged everywhere (older distributions): fall back
# to pip, for this user only.
_pasang_podman_compose_pip() {
    local pengelola="$1"
    if ! command -v pip3 >/dev/null 2>&1 && ! python3 -m pip --version >/dev/null 2>&1; then
        case "$pengelola" in
            pacman) _pasang_paket "$pengelola" python-pip ;;
            apk) _pasang_paket "$pengelola" py3-pip ;;
            *) _pasang_paket "$pengelola" python3-pip ;;
        esac
    fi
    if [ "${PASANG_SIMULASI:-}" = "1" ]; then
        echo "[simulasi] python3 -m pip install --user podman-compose"
        return 0
    fi
    # --break-system-packages: newer pips refuse --user installs on a
    # distribution-managed Python; older ones don't know the flag.
    python3 -m pip install --user podman-compose 2>/dev/null \
        || python3 -m pip install --user --break-system-packages podman-compose
    export PATH="$HOME/.local/bin:$PATH"
}

# Whether ``$2`` (/etc/subuid or /etc/subgid) has a line for user ``$1``.
# Plain bash: this runs before anything is known to be installed.
_punya_subid() {
    local baris
    [ -f "$2" ] || return 1
    while IFS= read -r baris; do
        case "$baris" in "$1":*) return 0 ;; esac
    done < "$2"
    return 1
}

# Rootless podman maps the user onto a range of sub-ids; a user made without
# one (some minimal images, users added by hand) cannot run containers.
_siapkan_rootless() {
    [ "$(id -u)" -eq 0 ] && return 0
    local pengguna
    pengguna="$(id -un)"
    local berkas
    for berkas in /etc/subuid /etc/subgid; do
        if ! _punya_subid "$pengguna" "$berkas"; then
            echo "Menambah rentang sub-id untuk ${pengguna} di ${berkas}..."
            if [ "$berkas" = /etc/subuid ]; then
                _jalankan usermod --add-subuids 100000-165535 "$pengguna" || true
            else
                _jalankan usermod --add-subgids 100000-165535 "$pengguna" || true
            fi
            _SUBID_DIUBAH=1
        fi
    done
    if [ -n "${_SUBID_DIUBAH:-}" ] && [ "${PASANG_SIMULASI:-}" != "1" ] && command -v podman >/dev/null 2>&1; then
        podman system migrate >/dev/null 2>&1 || true
    fi
}

pasang_komponen() {
    local kurang=() perintah
    for perintah in "$@"; do
        command -v "$perintah" >/dev/null 2>&1 || kurang+=("$perintah")
    done
    if [ "${#kurang[@]}" -eq 0 ]; then
        return 0
    fi

    echo "Komponen belum terpasang: ${kurang[*]} — memasang otomatis..."
    local pengelola
    if ! pengelola="$(_pengelola_paket)"; then
        echo "Tidak menemukan pengelola paket (apt, dnf, yum, zypper, pacman, apk). Pasang sendiri: ${kurang[*]}" >&2
        return 1
    fi

    for perintah in "${kurang[@]}"; do
        if ! _pasang_paket "$pengelola" "$(_paket "$perintah" "$pengelola")"; then
            if [ "$perintah" = "podman-compose" ]; then
                echo "Paket podman-compose tidak tersedia di $pengelola — memasang lewat pip..."
                _pasang_podman_compose_pip "$pengelola"
            else
                echo "Gagal memasang $perintah. Pasang sendiri lalu jalankan lagi." >&2
                return 1
            fi
        fi
        if [ "$perintah" = "podman" ]; then
            # Best effort, one by one: a name unknown to this release must not stop the rest.
            local pendamping
            for pendamping in $(_paket_pendamping_podman "$pengelola"); do
                _pasang_paket "$pengelola" "$pendamping" >/dev/null 2>&1 \
                    || echo "(lewati $pendamping: tidak tersedia di $pengelola)"
            done
            _siapkan_rootless
        fi
    done

    if [ "${PASANG_SIMULASI:-}" = "1" ]; then
        return 0
    fi
    hash -r
    for perintah in "${kurang[@]}"; do
        if ! command -v "$perintah" >/dev/null 2>&1; then
            echo "$perintah masih belum ditemukan setelah dipasang. Pasang sendiri lalu jalankan lagi." >&2
            return 1
        fi
    done
    echo "Komponen terpasang: ${kurang[*]}"
}

# The last check before the stack starts: podman itself answers (a broken
# rootless setup fails here with a readable message instead of mid-compose).
periksa_podman() {
    if [ "${PASANG_SIMULASI:-}" = "1" ]; then
        return 0
    fi
    if ! podman info >/dev/null 2>&1; then
        echo "podman terpasang tetapi belum bisa dijalankan oleh pengguna $(id -un)." >&2
        echo "Coba: 'podman system migrate', lalu keluar-masuk sesi (login ulang) dan jalankan lagi." >&2
        podman info 2>&1 | tail -3 >&2 || true
        return 1
    fi
}
