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

# django-bolt's static serving looks for STATIC_ROOT (/app/staticfiles), which
# only gets populated by `collectstatic` — and that only runs during prod's
# image build (Containerfile), never in dev. Symlinking it to the same
# source static/ dir STATICFILES_DIRS already serves from (not static/dist —
# that would break /static/vendor/*, a sibling of dist/, not a child of it)
# silences django-bolt's "cannot resolve directory" warning without
# duplicating any files or needing collectstatic in dev at all.
if [ ! -e staticfiles ]; then
    ln -s static staticfiles
fi

# Detect the host's LAN IP so phones/devices on the same network can open the
# app without touching .env.dev. Shell env vars override --env-file values in
# podman-compose, so this export wins over whatever DJANGO_ALLOWED_HOSTS the
# file has.
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
# Wildcard so any host (LAN IP, tunnel URL) is allowed in dev.
export DJANGO_ALLOWED_HOSTS="*"
# Trust HTTPS tunnel origins for CSRF (localtonet, ngrok, etc.).
# Set this to your tunnel URL, e.g. https://abc123.localtonet.com
export DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS:-}"
echo "Dev server: http://localhost:8001${LOCAL_IP:+ | http://$LOCAL_IP:8001}"
echo "Tunnel (HTTPS): set DJANGO_CSRF_TRUSTED_ORIGINS=https://your-tunnel-url before running"

# Tear down any existing containers for this stack first. dev and prod share
# service names (postgres/valkey/garage/pgbouncer) from the base compose.yml,
# so a leftover prod run left running/stopped would otherwise get reused
# as-is by `up` — stale env vars, stale bind-mount paths (e.g. a since-deleted
# worktree) — instead of being recreated against this run's config.
# --remove-orphans also clears prod-only containers (app1/app2/app3/nginx/
# static-sync) that aren't part of this dev overlay at all.
podman-compose --env-file "$(pwd)/.env.dev" -f podman/compose.yml -f podman/compose.dev.yml down --remove-orphans

podman-compose --env-file "$(pwd)/.env.dev" -f podman/compose.yml -f podman/compose.dev.yml up
