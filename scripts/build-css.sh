#!/usr/bin/env bash
set -euo pipefail

VERSION="v4.3.3"
BIN="bin/tailwindcss"

if [ ! -f "$BIN" ]; then
    mkdir -p bin
    ARCH="$(uname -m)"
    case "$ARCH" in
        aarch64|arm64) ASSET="tailwindcss-linux-arm64" ;;
        x86_64) ASSET="tailwindcss-linux-x64" ;;
        *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
    esac
    curl -sL -o "$BIN" "https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSION}/${ASSET}"
    chmod +x "$BIN"
fi

mkdir -p static/dist
"$BIN" -i static/src/input.css -o static/dist/output.css --minify
