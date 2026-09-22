# Podman Infra (dev.sh / prod.sh) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full stack (app + PostgreSQL/PgBouncer + Valkey + Garage) under Podman, with a `dev.sh` (bind-mounted, auto-reload) and a `prod.sh` (built image, multi-process, first-run secret generation).

**Architecture:** A multi-stage `Containerfile` builds the app on `python:3.14-slim` with `uv`. `podman-compose` layers a base `podman/compose.yml` (the four backing services) under environment-specific overrides (`compose.dev.yml`, `compose.prod.yml`) for the `app` service, which differs significantly between the two (bind-mount + `runbolt --dev` vs. built image + `runbolt --processes N`).

**Tech Stack:** Podman 4.9.3, podman-compose 1.0.6 (both confirmed installed), `postgres:17-alpine`, `edoburu/pgbouncer`, `valkey/valkey:8-alpine`, `dxflrs/garage:v2.3.0`, `python:3.14-slim`, `uv` 0.12.17 (copied from `ghcr.io/astral-sh/uv:0.12.17`), django-bolt's `manage.py runbolt` as the app server.

**Spec:** `docs/superpowers/specs/2026-09-22-podman-infra-design.md`

## Global Constraints

- No changes to `core/`, `templates/`, or `harwat_main/` — this sub-project is purely
  infrastructure, additive only. (`README.md` at repo root is docs, not app code — extending it
  is in scope.)
- The app container runs via django-bolt's own `manage.py runbolt` management command — **never**
  gunicorn or uvicorn. `runbolt` serves standard Django views and any `BoltAPI` routes together in
  one process.
- **Correction from the spec:** the spec said PgBouncer "exposes port 6432" — the `edoburu/pgbouncer`
  image actually listens on **5432** by default ("uses standard Postgres port 5432, to work
  transparently for applications", per the image's own docs). This plan uses 5432, not 6432.
- **Correction/addition beyond the spec:** the spec's Garage bootstrap section says
  `GARAGE_RPC_SECRET` is "stored the same way as other secrets" — Garage actually requires
  `rpc_secret` to be a field **inside `garage.toml`**, not an environment variable the `garage`
  binary reads directly. This plan generates `podman/garage.prod.toml` from a template at
  `prod.sh` first-run time (via `envsubst`), rather than passing it as a container env var.
  Dev uses a fixed, committed, non-secret `garage.dev.toml` instead (consistent with `.env.dev`
  being non-sensitive placeholders).
- **Addition beyond the spec (dev correctness):** bind-mounting the whole repo into the dev `app`
  container's `/app` would also shadow the image's baked `/app/.venv` (installed by the
  Containerfile's `builder` stage) with whatever the host has at `.venv/` — breaking dependency
  resolution, or mounting an empty directory if the host has no `.venv`. `compose.dev.yml`
  protects against this with a named volume mounted specifically at `/app/.venv`, layered on top
  of the bind mount (both Podman and Docker copy an image's existing directory content into a
  fresh named volume on first use, so the builder stage's installed dependencies populate it
  correctly on first `dev.sh` run).
- **Ruling — narrow, deliberate exception to "no `harwat_main/` changes":** the spec's Scope
  section explicitly promises `prod.sh` brings the app up with "DEBUG off." `harwat_main/settings.py`
  currently hardcodes `DEBUG = True` with no env-var hook at all. Leaving it hardcoded would mean
  `prod.sh` silently ships a Django app with `DEBUG=True` in production — not merely incomplete
  infrastructure wiring (like the deferred `DATABASE_URL`/`REDIS_URL` consumption below), but an
  active, well-known Django security misconfiguration (stack traces, settings, and SQL queries
  leak to any visitor who triggers a 500). Task 4 therefore makes one minimal, additive change to
  `harwat_main/settings.py`: read `DEBUG` from a `DJANGO_DEBUG` environment variable, **defaulting
  to `True`** so existing dev workflows (`manage.py runserver`/`test` outside Podman entirely) are
  completely unaffected. This is the one exception to "no `harwat_main/` changes" in this plan —
  everything else (`DATABASE_URL`, `REDIS_URL`, S3/Garage config) stays unwired, per the spec,
  because those are incompleteness, not a live vulnerability.
- Exact image versions/pins (do not substitute): `postgres:17-alpine`, `edoburu/pgbouncer`
  (no version pin available/needed — see Task 1), `valkey/valkey:8-alpine`,
  `dxflrs/garage:v2.3.0`, `python:3.14-slim`, `ghcr.io/astral-sh/uv:0.12.17`.
- Garage config fields (confirmed against Garage's own quick-start docs): `metadata_dir`,
  `data_dir`, `db_engine`, `replication_factor`, `rpc_bind_addr`, `rpc_public_addr`, `rpc_secret`,
  and an `[s3_api]` section (`s3_region`, `api_bind_addr`, `root_domain`).
- No automated test suite for this sub-project — it's infrastructure config, not application
  logic (per spec's Testing/verification section). Each task instead has a real, runnable
  verification step (`podman-compose ... config` for fast syntax/merge validation without pulling
  images; `podman build` for the Containerfile, which does need network access).
- `uv sync` in the Containerfile uses `--frozen` only (no `--no-dev` — this project's
  `pyproject.toml` has no dev-dependency group to exclude).
- Run every Python/Django command referenced in scripts through the container's own venv
  (`PATH` includes `/app/.venv/bin`) or via `uv run` in the builder stage — never bare `python`
  assuming a system install.

---

### Task 1: Base compose services (`podman/compose.yml`) + Garage config + dev env template

**Files:**
- Create: `podman/compose.yml`
- Create: `podman/garage.dev.toml`
- Create: `podman/garage.toml.template`
- Create: `.env.dev.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: compose service names `postgres`, `pgbouncer`, `valkey`, `garage` and named volumes
  `pgdata`, `valkey-data`, `garage-data`, `garage-meta` — consumed by `compose.dev.yml`/
  `compose.prod.yml` (Tasks 3/4) via `-f podman/compose.yml -f podman/compose.<env>.yml` layering.
  Env var names `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (read by `postgres` and
  `pgbouncer`), `GARAGE_DEFAULT_ACCESS_KEY`/`GARAGE_DEFAULT_SECRET_KEY`/`GARAGE_DEFAULT_BUCKET`
  (read by `garage`, dev-only — Task 3 wires these into the `garage` override) — later tasks reuse
  these exact names.

- [ ] **Step 1: Add gitignore entries for the two env files this plan introduces**

Append to `.gitignore`:

```
# Podman infra secrets (generated/copied locally, never committed)
.env.dev
.env.prod
podman/garage.prod.toml
```

- [ ] **Step 2: Write the dev Garage config (fixed, non-secret, committed)**

Create `podman/garage.dev.toml`:

```toml
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "sqlite"

replication_factor = 1

rpc_bind_addr = "[::]:3901"
rpc_public_addr = "garage:3901"
rpc_secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.bmn-harwat.local"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.bmn-harwat.local"

[admin]
api_bind_addr = "[::]:3903"
```

(`rpc_secret` here is a fixed, publicly-known 64-hex-char dev placeholder — fine to commit, this
config is only ever mounted into the dev `garage` container, never prod.)

- [ ] **Step 3: Write the prod Garage config template**

Create `podman/garage.toml.template` (identical structure, `rpc_secret` is a placeholder
`envsubst` fills in at `prod.sh` first-run time — see Task 4):

```toml
metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "sqlite"

replication_factor = 1

rpc_bind_addr = "[::]:3901"
rpc_public_addr = "garage:3901"
rpc_secret = "${GARAGE_RPC_SECRET}"

[s3_api]
s3_region = "garage"
api_bind_addr = "[::]:3900"
root_domain = ".s3.bmn-harwat.local"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.bmn-harwat.local"

[admin]
api_bind_addr = "[::]:3903"
```

- [ ] **Step 4: Write the base compose file**

Create `podman/compose.yml`:

```yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-bmn_harwat}
      POSTGRES_USER: ${POSTGRES_USER:-bmn_harwat}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  pgbouncer:
    image: edoburu/pgbouncer
    environment:
      DB_HOST: postgres
      DB_USER: ${POSTGRES_USER:-bmn_harwat}
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_NAME: ${POSTGRES_DB:-bmn_harwat}
      POOL_MODE: transaction
    depends_on:
      - postgres
    restart: unless-stopped

  valkey:
    image: valkey/valkey:8-alpine
    command: ["valkey-server", "--appendonly", "yes"]
    volumes:
      - valkey-data:/data
    restart: unless-stopped

  garage:
    image: dxflrs/garage:v2.3.0
    ports:
      - "3900:3900"
      - "3901:3901"
      - "3902:3902"
      - "3903:3903"
    volumes:
      - garage-data:/var/lib/garage/data
      - garage-meta:/var/lib/garage/meta
    restart: unless-stopped

volumes:
  pgdata:
  valkey-data:
  garage-data:
  garage-meta:
```

- [ ] **Step 5: Write the dev env var template**

Create `.env.dev.example` (non-sensitive placeholder values — a developer copies this to
`.env.dev`, done automatically by `dev.sh` in Task 3):

```
POSTGRES_DB=bmn_harwat
POSTGRES_USER=bmn_harwat
POSTGRES_PASSWORD=dev-only-not-secret
GARAGE_DEFAULT_ACCESS_KEY=dev-access-key
GARAGE_DEFAULT_SECRET_KEY=dev-secret-key-not-secret
GARAGE_DEFAULT_BUCKET=bmn-harwat-dev
DJANGO_SECRET_KEY=dev-only-not-secret-django-key
DATABASE_URL=postgres://bmn_harwat:dev-only-not-secret@pgbouncer:5432/bmn_harwat
REDIS_URL=redis://valkey:6379/0
```

(`DATABASE_URL`/`REDIS_URL` are set for forward compatibility — nothing in `harwat_main/settings.py`
reads them yet, per this plan's Global Constraints. They're here so the `app` service's
environment is ready for whenever a future plan wires Django to consume them.)

- [ ] **Step 6: Verify the compose file is syntactically valid**

Run: `podman-compose -f podman/compose.yml config`

Expected: prints the fully-resolved YAML (with `${POSTGRES_PASSWORD}` etc. shown as empty/warned
since no `.env` is loaded yet at this step — that's fine, this step only checks YAML/schema
validity, not runtime values). Exit code 0. If it errors on YAML syntax, fix `podman/compose.yml`
before continuing.

- [ ] **Step 7: Commit**

```bash
git add .gitignore podman/compose.yml podman/garage.dev.toml podman/garage.toml.template .env.dev.example
git commit -m "Add base Podman compose services (Postgres+PgBouncer, Valkey, Garage)"
```

---

### Task 2: Containerfile

**Files:**
- Create: `Containerfile`

**Interfaces:**
- Consumes: `static/dist/output.css` and `static/vendor/*.js` (from the login-dashboard-ui
  sub-project, already merged to master) — must exist in the build context before building, via
  `./scripts/build-css.sh` (this task's verification step runs it first).
- Produces: two build targets, `builder` (deps installed at `/app/.venv`, consumed by
  `compose.dev.yml`'s `target: builder` in Task 3) and `final` (the complete runnable image,
  consumed by `compose.prod.yml`'s `target: final` in Task 4). `CMD` invokes
  `python manage.py runbolt --host 0.0.0.0 --port 8000 --processes 4 --respawn-failed-workers`.

- [ ] **Step 1: Write the Containerfile**

Create `Containerfile` (repo root):

```dockerfile
# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .


FROM python:3.14-slim AS final

RUN groupadd --system app && useradd --system --gid app --home /app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:${PATH}"

RUN python manage.py collectstatic --noinput

USER app

EXPOSE 8000

CMD ["python", "manage.py", "runbolt", "--host", "0.0.0.0", "--port", "8000", "--processes", "4", "--respawn-failed-workers"]
```

(The `final` stage needs no `uv` binary at all — `PATH` puts the venv's own `python` first, so
`python manage.py ...` runs directly against the installed dependencies. `--processes 4` is a
starting default; an operator can override via `docker/podman run`'s command override or by
editing this line later — the spec left the exact number "decided at plan time," and 4 is a
reasonable default for a small VM/host without knowing the target hardware.)

- [ ] **Step 2: Ensure the build context has what the image needs, then build it**

The `final` stage's `collectstatic` step needs `static/dist/output.css` to exist (it's a
gitignored build artifact from the login-dashboard-ui sub-project, not present in a fresh clone).
Build it first:

```bash
./scripts/build-css.sh
```

Expected: exits 0, `static/dist/output.css` now exists (from the already-merged Task 1 of the
login-dashboard-ui plan — this repeats a step that plan's own instructions covered, just ensuring
it's actually present before the container build needs it).

Then build both targets:

```bash
podman build -f Containerfile --target builder -t bmn-harwat:builder .
podman build -f Containerfile --target final -t bmn-harwat:final .
```

Expected: both exit 0. This step requires network access (pulls `python:3.14-slim` and
`ghcr.io/astral-sh/uv:0.12.17`) and may take a few minutes on first run. If the `final` build
fails at the `collectstatic` step with a missing-static-file error, `static/dist/output.css` or
`static/vendor/*.js` is missing from the build context — re-run `./scripts/build-css.sh` and
confirm `static/vendor/htmx.min.js` / `static/vendor/alpinejs.min.js` exist (they're committed,
should already be there from the merged login-dashboard-ui work).

- [ ] **Step 3: Sanity-check the built image runs `runbolt` without crashing on startup**

```bash
podman run --rm bmn-harwat:final python manage.py check
```

Expected: `System check identified no issues (0 silenced).` — this doesn't need a database
connection (`manage.py check` doesn't query the DB), so it should pass even though no Postgres
container is running in this isolated check.

- [ ] **Step 4: Commit**

```bash
git add Containerfile
git commit -m "Add multi-stage Containerfile using django-bolt's runbolt server"
```

---

### Task 3: Dev override + `dev.sh`

**Files:**
- Create: `podman/compose.dev.yml`
- Create: `dev.sh`

**Interfaces:**
- Consumes: `podman/compose.yml` (Task 1, service/volume names), `Containerfile`'s `builder`
  target (Task 2), `.env.dev.example` (Task 1, copied to `.env.dev` by this task's script).
- Produces: nothing consumed by later tasks — `dev.sh` is a leaf script, mirrored (not shared)
  by `prod.sh` in Task 4.

- [ ] **Step 1: Write the dev compose override**

Create `podman/compose.dev.yml`:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Containerfile
      target: builder
    command: ["python", "manage.py", "runbolt", "--dev", "--host", "0.0.0.0", "--port", "8000"]
    volumes:
      - .:/app
      - app-dev-venv:/app/.venv
    environment:
      DJANGO_DEBUG: "True"
      DATABASE_URL: ${DATABASE_URL}
      REDIS_URL: ${REDIS_URL}
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - pgbouncer
      - valkey
      - garage
    working_dir: /app

  garage:
    environment:
      GARAGE_DEFAULT_ACCESS_KEY: ${GARAGE_DEFAULT_ACCESS_KEY}
      GARAGE_DEFAULT_SECRET_KEY: ${GARAGE_DEFAULT_SECRET_KEY}
      GARAGE_DEFAULT_BUCKET: ${GARAGE_DEFAULT_BUCKET}
    volumes:
      - ./podman/garage.dev.toml:/etc/garage.toml:ro
    command: ["/garage", "server", "--single-node", "--default-bucket"]

volumes:
  app-dev-venv:
```

(The `builder` target already has deps installed via `uv sync --frozen` at image-build time; the
`.:/app` bind mount overlays live source code, and the separate `app-dev-venv` named volume
protects `/app/.venv` from being shadowed by that mount — see the Global Constraints note.
`--dev` on `runbolt` gives auto-reload, so code edits take effect without a container restart;
only a dependency change requires `podman-compose ... build` again.)

- [ ] **Step 2: Write `dev.sh`**

Create `dev.sh` (repo root):

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.dev ]; then
    cp .env.dev.example .env.dev
    echo ".env.dev created from .env.dev.example — edit if you need different local values (all defaults are non-sensitive)."
fi

podman-compose --env-file .env.dev -f podman/compose.yml -f podman/compose.dev.yml up
```

Make it executable: `chmod +x dev.sh`

- [ ] **Step 3: Verify the merged compose config is valid**

```bash
cp .env.dev.example .env.dev
podman-compose --env-file .env.dev -f podman/compose.yml -f podman/compose.dev.yml config
```

Expected: prints the fully-resolved YAML with the `app` service's `build`/`volumes`/`command`
overrides applied and every `${VAR}` substituted from `.env.dev` (no bare `${...}` left in the
output — if you see one, its name is missing from `.env.dev.example`, fix Task 1's file). Exit
code 0.

(This step created a real `.env.dev` from the example — leave it in place, `dev.sh` checks for
its existence too and won't overwrite it.)

- [ ] **Step 4: Operational verification (manual, not gated — run if you have time/network for a full stack pull)**

This step has no automated assertion; it's a real end-to-end check the config-validation in Step
3 can't provide (image pulls, container startup, actual HTTP reachability).

```bash
./dev.sh
```

In another terminal, once containers report ready (watch the `dev.sh` output):

```bash
podman-compose --env-file .env.dev -f podman/compose.yml -f podman/compose.dev.yml ps
curl -sf http://localhost:8000/login/ | head -5
podman exec -it $(podman-compose --env-file .env.dev -f podman/compose.yml -f podman/compose.dev.yml ps -q garage) /garage bucket list
```

Expected: all 5 services (`postgres`, `pgbouncer`, `valkey`, `garage`, `app`) show as running; the
`curl` returns the login page's HTML (starts with `<!DOCTYPE html>`); `garage bucket list` shows
the `bmn-harwat-dev` default bucket. Stop with Ctrl-C in the first terminal when done.

- [ ] **Step 5: Commit**

```bash
git add podman/compose.dev.yml dev.sh
git commit -m "Add dev.sh: bind-mounted, auto-reloading Podman dev stack"
```

---

### Task 4: Prod override + `prod.sh`

**Files:**
- Create: `podman/compose.prod.yml`
- Create: `prod.sh`
- Modify: `harwat_main/settings.py` (the narrow DEBUG exception ruled on in Global Constraints)

**Interfaces:**
- Consumes: `podman/compose.yml` (Task 1), `Containerfile`'s `final` target (Task 2),
  `podman/garage.toml.template` (Task 1).
- Produces: nothing consumed by later tasks — leaf script, mirrors `dev.sh` (Task 3).

- [ ] **Step 1: Make `DEBUG` environment-driven (defaulting to unchanged behavior)**

Modify `harwat_main/settings.py`. Add `import os` near the top (alongside the existing
`from pathlib import Path`):

```python
import os
from pathlib import Path
```

Then change the hardcoded `DEBUG = True` line to:

```python
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'
```

Verify nothing outside Podman changes behavior: `uv run python manage.py test` (no `DJANGO_DEBUG`
set in your normal shell) should still show `DEBUG` resolving to `True` exactly as before — run:

```bash
uv run python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'harwat_main.settings'); django.setup(); from django.conf import settings; print(settings.DEBUG)"
```

Expected: `True` (unchanged from before this edit, since `DJANGO_DEBUG` isn't set in this shell).
Then confirm the override direction works:

```bash
DJANGO_DEBUG=False uv run python -c "import django; import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'harwat_main.settings'); django.setup(); from django.conf import settings; print(settings.DEBUG)"
```

Expected: `False`.

- [ ] **Step 2: Write the prod compose override**

Create `podman/compose.prod.yml`:

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Containerfile
      target: final
    env_file:
      - .env.prod
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - pgbouncer
      - valkey
      - garage
    restart: unless-stopped

  garage:
    volumes:
      - ./podman/garage.prod.toml:/etc/garage.toml:ro
    command: ["/garage", "server"]
```

(No `--single-node --default-bucket` and no `GARAGE_DEFAULT_*` env vars here — prod's Garage
cluster bootstrap is the deliberately-manual runbook from Task 5. `env_file: .env.prod` covers
`POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_USER` for the base `postgres`/`pgbouncer` services
too, since those already read `${POSTGRES_PASSWORD}` etc. from `podman/compose.yml` — any
compose-loaded env var is visible to every service's variable substitution, not just `app`'s.)

- [ ] **Step 3: Write `prod.sh`**

Create `prod.sh` (repo root):

```bash
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

podman-compose --env-file .env.prod -f podman/compose.yml -f podman/compose.prod.yml up -d --build
```

Make it executable: `chmod +x prod.sh`

(`.env.prod` is generated exactly once — the `if [ ! -f .env.prod ]` guard means re-running
`prod.sh` for a redeploy never rotates secrets under a running database. The `envsubst` call
regenerates `podman/garage.prod.toml` every run, which is fine — it's deterministic given the
same `GARAGE_RPC_SECRET`, and cheap to redo. `DJANGO_DEBUG=False` is the line that actually
delivers the "DEBUG off" the spec promised — Step 1's settings.py change is what makes this line
do anything.)

- [ ] **Step 4: Verify the merged compose config is valid (without generating real secrets yet)**

```bash
DJANGO_DEBUG=False DJANGO_SECRET_KEY=test POSTGRES_DB=test POSTGRES_USER=test POSTGRES_PASSWORD=test GARAGE_RPC_SECRET=0000000000000000000000000000000000000000000000000000000000000000 \
  bash -c 'echo "DJANGO_DEBUG=$DJANGO_DEBUG
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GARAGE_RPC_SECRET=$GARAGE_RPC_SECRET" > .env.prod.test'
envsubst '${GARAGE_RPC_SECRET}' < podman/garage.toml.template > /tmp/garage.prod.test.toml
grep -c '0000000000' /tmp/garage.prod.test.toml
podman-compose --env-file .env.prod.test -f podman/compose.yml -f podman/compose.prod.yml config
rm -f .env.prod.test /tmp/garage.prod.test.toml
```

Expected: the `grep -c` prints `1` (confirming `envsubst` actually substituted the placeholder —
not left `${GARAGE_RPC_SECRET}` literally in the output), and `podman-compose ... config` prints
the fully-resolved YAML with no bare `${...}` left anywhere. Exit code 0. (This step deliberately
uses throwaway test values, not `prod.sh` itself, so it doesn't create a real `.env.prod` with a
real generated secret before you're ready to.)

- [ ] **Step 5: Operational verification (manual, not gated — this actually runs `prod.sh` and generates real local secrets)**

```bash
./prod.sh
```

Expected: `.env.prod` is created (first run only — check its content is 6 lines, all populated,
no empty values, including `DJANGO_DEBUG=False`). `podman/garage.prod.toml` is created with the
real generated `rpc_secret` substituted in (not the literal `${GARAGE_RPC_SECRET}` string —
`grep GARAGE_RPC_SECRET podman/garage.prod.toml` should print nothing). The stack comes up
detached (`podman-compose --env-file .env.prod -f podman/compose.yml -f podman/compose.prod.yml
ps` shows all 5 services running). `curl -sf http://localhost:8000/login/ | head -5` returns the
login page's HTML. Trigger a 500 (e.g. temporarily hit a nonexistent view path that isn't a
normal 404, or check the container logs directly) and confirm no Django debug traceback page is
served — a production error page or plain 500, not a stack trace with settings dumped.

Run `./prod.sh` a second time and confirm `.env.prod`'s content (or mtime) is unchanged — it
should print no "Generating .env.prod" line the second time, only bring the stack back up.

- [ ] **Step 6: Commit**

```bash
git add harwat_main/settings.py podman/compose.prod.yml prod.sh
git commit -m "Add prod.sh: built image, multi-process runbolt, DEBUG=False, first-run secret generation"
```

---

### Task 5: Garage prod-bootstrap runbook + README

**Files:**
- Create: `docs/podman-garage-prod-setup.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new (documents the running system from Tasks 1-4).
- Produces: nothing — final, documentation-only task.

- [ ] **Step 1: Write the Garage production bootstrap runbook**

Create `docs/podman-garage-prod-setup.md`:

```markdown
# Garage production cluster bootstrap

`prod.sh` starts the `garage` container but does **not** auto-configure its cluster layout,
bucket, or access key — that's deliberate (see the Podman infra design spec's Garage bootstrap
section: auto-generating production S3 credentials on every fresh `prod.sh` run would leak them
into container logs on first boot). Run these steps once, after `./prod.sh` has brought the stack
up for the first time.

Find the garage container name/id:

```bash
GARAGE=$(podman-compose --env-file .env.prod -f podman/compose.yml -f podman/compose.prod.yml ps -q garage)
```

## 1. Assign and apply the single-node layout

```bash
podman exec -it "$GARAGE" /garage status
```

Copy the node ID shown, then:

```bash
podman exec -it "$GARAGE" /garage layout assign -z dc1 -c 1G <node-id>
podman exec -it "$GARAGE" /garage layout apply --version 1
```

## 2. Create the application bucket

```bash
podman exec -it "$GARAGE" /garage bucket create bmn-harwat-prod
```

## 3. Create an access key and grant it permissions

```bash
podman exec -it "$GARAGE" /garage key create bmn-harwat-app-key
podman exec -it "$GARAGE" /garage bucket allow \
  --read --write \
  bmn-harwat-prod \
  --key bmn-harwat-app-key
```

`garage key create`'s output includes the access key ID and secret key — copy both immediately
(the secret is only shown once) and store them wherever this deployment's other production
secrets live. They are **not** written to `.env.prod` by any script; that file only holds the
`GARAGE_RPC_SECRET` used for the cluster's internal RPC authentication, not S3 application
credentials.

## Verifying

```bash
podman exec -it "$GARAGE" /garage bucket list
podman exec -it "$GARAGE" /garage bucket info bmn-harwat-prod
```

Both should show the `bmn-harwat-prod` bucket with the key from step 3 attached.
```

- [ ] **Step 2: Add a Podman section to README.md**

Read the current `README.md` first (it already has a "Development setup" section from the
login-dashboard-ui plan — don't remove or duplicate it). Append a new section after it:

```markdown

## Running with Podman

The full stack (app, PostgreSQL+PgBouncer, Valkey, Garage) runs under Podman via
`podman-compose`. See `docs/superpowers/specs/2026-09-22-podman-infra-design.md` for the full
design.

```bash
./dev.sh    # local dev: bind-mounted code, auto-reload, DEBUG on
./prod.sh   # production: built image, multi-process, secrets auto-generated into .env.prod on first run
```

Production also needs a one-time manual Garage cluster bootstrap after the first `./prod.sh` —
see `docs/podman-garage-prod-setup.md`.

**Note:** the app container itself still runs against SQLite today (`harwat_main/settings.py`'s
`DATABASES` is unchanged by this sub-project) — the Postgres/PgBouncer/Valkey/Garage containers
come up and are reachable, but Django isn't wired to use them yet. That wiring is a separate,
future piece of work.
```

- [ ] **Step 3: Verify the runbook and README are internally consistent**

Re-read both files. Confirm: every command in `docs/podman-garage-prod-setup.md` uses the exact
compose invocation pattern (`--env-file .env.prod -f podman/compose.yml -f
podman/compose.prod.yml`) established in Task 4's `prod.sh`, not a different/simplified one that
would actually fail if copy-pasted. Confirm the README's note about SQLite matches this plan's
Global Constraints (no `harwat_main/settings.py` changes) — this is the single most important
sentence in this task, since it's the one thing stopping someone from assuming the containers
being "up" means the app is actually using them.

- [ ] **Step 4: Commit**

```bash
git add docs/podman-garage-prod-setup.md README.md
git commit -m "Add Garage prod-bootstrap runbook and Podman section to README"
```
