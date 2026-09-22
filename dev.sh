#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.dev ]; then
    cp .env.dev.example .env.dev
    echo ".env.dev created from .env.dev.example — edit if you need different local values (all defaults are non-sensitive)."
fi

podman-compose --env-file "$(pwd)/.env.dev" -f podman/compose.yml -f podman/compose.dev.yml up
