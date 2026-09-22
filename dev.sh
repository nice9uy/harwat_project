#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# podman-compose 1.0.6 resolves relative paths in layered `-f` files against
# the directory of the FIRST `-f` file (podman/), not the caller's CWD. That's
# why --env-file below uses an absolute path instead of a bare filename, and
# why podman/compose.dev.yml's build context / bind-mount paths use `..`
# (repo root) instead of `.`.

if [ ! -f .env.dev ]; then
    cp .env.dev.example .env.dev
    echo ".env.dev created from .env.dev.example — edit if you need different local values (all defaults are non-sensitive)."
fi

# Podman's collectstatic (and this compose's static asset serving) needs
# static/dist/output.css, a Tailwind build artifact that isn't in git. Build
# it automatically if it's missing so a fresh checkout doesn't silently ship
# a visually broken app (collectstatic succeeds either way — it doesn't fail
# loudly if this file is absent, so the guard has to happen here instead).
if [ ! -f static/dist/output.css ]; then
    ./scripts/build-css.sh
fi

podman-compose --env-file "$(pwd)/.env.dev" -f podman/compose.yml -f podman/compose.dev.yml up
