#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

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

if ! command -v envsubst >/dev/null 2>&1; then
    echo "envsubst not found (part of gettext) — install it before running prod.sh." >&2
    exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl not found — install it before running prod.sh." >&2
    exit 1
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

set -a
source .env.prod
set +a

# umask 077 also covers this regeneration (podman/garage.prod.toml is
# rewritten on every run, not just first-run) — re-set here so a run where
# .env.prod already existed (skipping the block above) still creates
# garage.prod.toml 0600 instead of the default 0644.
umask 077
envsubst '${GARAGE_RPC_SECRET}' < podman/garage.toml.template > podman/garage.prod.toml

podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml up -d --build

# Idempotent — safe to run on every invocation, not just first-run. Nothing
# else in this stack ever runs migrations, and db.sqlite3 is schemaless on a
# fresh volume, so skipping this would leave every table missing.
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml exec -T app1 python manage.py migrate --noinput
