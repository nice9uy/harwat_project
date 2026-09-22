#!/usr/bin/env bash
set -euo pipefail

if ! command -v envsubst >/dev/null 2>&1; then
    echo "envsubst not found (part of gettext) — install it before running prod.sh." >&2
    exit 1
fi

if [ ! -f .env.prod ]; then
    echo "Generating .env.prod (first run)..."
    {
        echo "DJANGO_DEBUG=False"
        echo "DJANGO_SECRET_KEY=$(openssl rand -hex 32)"
        echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1"
        echo "POSTGRES_DB=bmn_harwat"
        echo "POSTGRES_USER=bmn_harwat"
        echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
        echo "GARAGE_RPC_SECRET=$(openssl rand -hex 32)"
    } > .env.prod
    echo ".env.prod created — back it up somewhere safe (it is gitignored)."
fi

set -a
source .env.prod
set +a

envsubst '${GARAGE_RPC_SECRET}' < podman/garage.toml.template > podman/garage.prod.toml

podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml up -d --build
