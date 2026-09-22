# Podman Infra — dev.sh / prod.sh Design Spec

Date: 2026-09-22
Status: Approved for implementation planning

## Context

`bmn_harwat`'s eventual target stack (declared during the earlier login+dashboard-UI spec,
`docs/superpowers/specs/2026-09-22-login-dashboard-ui-design.md`) includes Podman, PostgreSQL +
PgBouncer, Valkey (cache), and Garage (S3-compatible object storage). That spec explicitly
deferred all of this as a separate sub-project ("No Podman/container files in this pass"). This
spec covers that deferred sub-project: `dev.sh` and `prod.sh` scripts that run the full stack via
Podman.

Nothing containerization-related exists yet in the repo — no Containerfile, no compose file, no
podman scripts. `podman` 4.9.3 and `podman-compose` 1.0.6 are already installed on the dev
machine.

The Django app itself (`core` app: login + dashboard) is being built independently in a parallel
sub-project/worktree and is not blocked by or blocking this one — they touch disjoint files
(this spec adds a `Containerfile` at repo root and a new `podman/` directory; it does not touch
`core/`, `templates/`, or `harwat_main/`).

## Scope

This spec covers:
1. A multi-stage `Containerfile` for the Django-Bolt app.
2. `podman-compose` service definitions for PostgreSQL, PgBouncer, Valkey, and Garage, shared
   between dev and prod via a base + override file layout.
3. `dev.sh` — brings up the full stack for local development: bind-mounted code, django-bolt's
   `runbolt --dev` server (auto-reload), DEBUG on, Garage auto-bootstrapped as a single-node
   cluster.
4. `prod.sh` — brings up the full stack for production: built image, django-bolt's own `runbolt`
   server (multi-process), DEBUG off, secrets auto-generated into a gitignored `.env.prod` on
   first run if absent.
5. Documentation for the one-time manual Garage cluster bootstrap in production.

Out of scope: actually deploying anywhere (this is local/single-host Podman only — no Kubernetes,
no cloud-specific config); TLS/reverse-proxy termination (assumed handled separately, e.g. by
whatever sits in front of this host in a real deployment); CI/CD; backups.

## Approach: orchestration

Chosen: **`podman-compose` with a layered compose file structure** — a base file with the
service definitions common to dev and prod, plus one override file per environment for the `app`
service (which differs significantly between the two: bind-mount + dev server vs. built image +
production server).

Rejected: hand-written `podman run`/`podman pod` sequences directly in `dev.sh`/`prod.sh` —
`podman-compose` is already installed, and compose YAML is more legible and easier to extend than
a growing sequence of shell-scripted `podman run` invocations with manual network/volume wiring.

Files:
```
podman/
  compose.yml         # base: postgres, pgbouncer, valkey, garage
  compose.dev.yml      # override: app service (bind-mount, `runbolt --dev`, DEBUG=True) + garage dev env
  compose.prod.yml     # override: app service (built image, `runbolt --processes N`, DEBUG=False)
Containerfile           # multi-stage build for the app image (repo root, so build context = repo root)
dev.sh                  # wraps: podman-compose -f podman/compose.yml -f podman/compose.dev.yml up
prod.sh                 # generates .env.prod if missing, then:
                         # podman-compose -f podman/compose.yml -f podman/compose.prod.yml up -d --build
```

## Service definitions (`podman/compose.yml`, shared by dev and prod)

- **postgres** — image `postgres:17-alpine`. Volume `pgdata:/var/lib/postgresql/data`. Not
  exposed to the host (only reachable by other services on the compose network) — the app talks
  to it through PgBouncer, never directly.
- **pgbouncer** — image `edoburu/pgbouncer`. Sits in front of `postgres`; exposes port 6432 to
  the `app` service (pool mode `transaction`, pointed at `postgres:5432` via its own env-var
  config). Not exposed to the host in prod; may be exposed in dev for local debugging with a
  Postgres client.
- **valkey** — image `valkey/valkey:8-alpine`. Volume `valkey-data:/data` for persistence
  (`--appendonly yes`). Not exposed to the host.
- **garage** — image `dxflrs/garage:v2.3.0` (per Garage's own quick-start docs). Ports: 3900 (S3
  API), 3901 (RPC), 3902 (S3 web), 3903 (admin API). Volumes `garage-data:/var/lib/garage/data`
  and `garage-meta:/var/lib/garage/meta`. Config (`garage.toml`, mounted read-only into the
  container) sets `replication_factor = 1` (single-node) and an `rpc_secret` (a 32-byte hex
  string — generated once, stored the same way as other secrets, see Secrets below).

## Garage bootstrap

Garage's modern single-node quick-start avoids the older manual `garage layout assign`/`apply`
dance: starting the server with `--single-node --default-bucket` and the environment variables
`GARAGE_DEFAULT_ACCESS_KEY`, `GARAGE_DEFAULT_SECRET_KEY`, `GARAGE_DEFAULT_BUCKET` set causes
Garage to self-configure a single-node cluster with that default bucket and key on first start —
no separate bootstrap script needed.

- **Dev:** `compose.dev.yml`'s `garage` override sets those three env vars (from `.env.dev`,
  committed as `.env.dev.example` with placeholder values, real `.env.dev` gitignored) and passes
  `--single-node --default-bucket` as the container command. Fully automatic — `dev.sh` up and
  the bucket/key exist.
- **Prod:** `compose.prod.yml` does **not** pass `--single-node --default-bucket` or the default
  credential env vars. `prod.sh` only starts the container. A `docs/podman-garage-prod-setup.md`
  runbook (created by this plan) documents the one-time manual steps (`garage layout assign`,
  `garage layout apply`, `garage bucket create`, `garage key create` + `garage bucket allow`) an
  operator runs once against the running prod container — this stays manual and undocumented-as-
  automatic on purpose, since auto-creating production credentials on every fresh `prod.sh` run
  would be a standing security foot-gun (whoever can read the container's stdout/logs on first
  boot would see the generated key).

## Containerfile (the `app` image)

Multi-stage build, repo root context:

1. **`builder` stage** — `python:3.14-slim` base (matches the `requires-python = ">=3.14"` pin in
   `pyproject.toml`). Installs `uv` (via the official install script or `pip install uv` — pinned
   version, decided at plan time). Copies `pyproject.toml` + `uv.lock`, runs
   `uv sync --frozen --no-dev` to produce `/app/.venv` with exactly the locked dependencies
   (including `django-bolt`'s prebuilt wheel with its compiled Rust extension — no compiler
   toolchain needed in this image since a wheel is used, not a source build).
2. **`final` stage** — same slim base, copies `.venv` from `builder`, copies the application code
   (`harwat_main/`, `core/`, `templates/`, `static/`, `manage.py`), sets `PATH` to include the
   venv. Runs as a non-root user (created in this stage). `CMD` starts the app via django-bolt's
   own management command, **`manage.py runbolt`** — confirmed present in the installed
   `django-bolt` package (`django_bolt/management/commands/runbolt.py`): a Rust/Actix-powered
   server that serves standard Django views (our `core` app) and any `BoltAPI` routes together in
   one process, self-contained — **no gunicorn/uvicorn layered on top**, and `harwat_main/asgi.py`
   / `wsgi.py` are not used by this path (Django's default scaffolding, left in place but
   unreferenced by the container). `runbolt` takes `--host`/`--port` directly, plus
   production-hardening flags used only in prod: `--processes N` (multi-process), and optionally
   `--respawn-failed-workers` (auto-restart crashed workers). `N` and whether to enable the other
   worker-recycling flags (`--max-rss`, `--workers-lifetime`) are decided at plan time.
3. **Static files:** the image runs `manage.py collectstatic --noinput` during the `final` stage
   build (requires `static/dist/output.css` and `static/vendor/*.js` to already exist in the
   build context — i.e. the Tailwind build step from the login-dashboard-ui sub-project must have
   been run before building this image; not this spec's concern to enforce, just a precondition
   `prod.sh` documents).

## `dev.sh`

```bash
podman-compose -f podman/compose.yml -f podman/compose.dev.yml up
```

`compose.dev.yml`'s `app` service: bind-mounts the repo root into the container, runs
`manage.py runbolt --dev --host 0.0.0.0 --port 8000` (`--dev` enables django-bolt's own
auto-reload on file changes — no separate file-watcher tooling needed), sets `DEBUG=True` and
`DATABASE_URL`/`REDIS_URL`/S3 env vars pointing at the other compose services by their service
names (Podman's compose network gives each service a resolvable hostname). Reads secrets/config
from `.env.dev` (gitignored; `.env.dev.example` committed with placeholder values as the
template).

## `prod.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.prod ]; then
    echo "Generating .env.prod (first run)..."
    {
        echo "DJANGO_SECRET_KEY=$(openssl rand -hex 32)"
        echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
        echo "GARAGE_RPC_SECRET=$(openssl rand -hex 32)"
        # ... other secrets, finalized at plan time
    } > .env.prod
    echo ".env.prod created — back it up somewhere safe (it is gitignored)."
fi

podman-compose -f podman/compose.yml -f podman/compose.prod.yml up -d --build
```

`compose.prod.yml`'s `app` service: uses the built image (no bind mount), runs the `runbolt` `CMD`
baked into the Containerfile (`manage.py runbolt --host 0.0.0.0 --port 8000 --processes N
--respawn-failed-workers`, `N` decided at plan time), `DEBUG=False`, reads all secrets from
`.env.prod`.

## Secrets

`.env.prod` is generated once by `prod.sh` (as shown above) if it doesn't already exist, and is
gitignored. Re-running `prod.sh` never regenerates it — it only generates when the file is
absent, so redeploying doesn't rotate secrets out from under a running database. `.env.dev` is
similarly gitignored, but its values are non-sensitive local-dev placeholders (committed as
`.env.dev.example`), not generated — a developer copies the example file once.

## Testing / verification

There is no application logic to unit test here — this is infrastructure config. Verification is
operational:
- `dev.sh` brings up all four services plus `app`, `podman-compose ps` shows all containers
  running, the app is reachable at `http://localhost:8000/login/`, and Garage's default bucket
  exists (`podman exec` into the garage container and run `garage bucket list`).
- `prod.sh` builds the image successfully, brings up the stack in detached mode, `.env.prod` is
  created on first run and NOT recreated on a second run (diff the file's mtime or content across
  two runs).
- The Containerfile builds successfully in isolation (`podman build -f Containerfile .`) and the
  resulting image's `collectstatic` step succeeds (fails loudly if `static/dist/output.css` is
  missing, which is the intended precondition failure mode).

## Non-goals (explicit)

- No Kubernetes / cloud-specific deployment config.
- No TLS/reverse-proxy setup (out of scope — assumed to sit in front of this host separately).
- No CI/CD pipeline changes.
- No automatic production Garage cluster bootstrap (deliberately manual — see Garage bootstrap
  section).
- No changes to `core/`, `templates/`, or `harwat_main/` — this sub-project is purely
  infrastructure, additive only.
