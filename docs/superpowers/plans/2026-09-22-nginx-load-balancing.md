# nginx Load Balancing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put `nginx` in front of three `app` container replicas in production, load-balancing across them and serving static files directly from a shared volume instead of proxying them to Django.

**Architecture:** `podman/compose.prod.yml`'s single `app` service is replaced by three identical named services (`app1`/`app2`/`app3`, internal-only — no published port). A new `nginx` service takes over the host's published port, load-balances across the three replicas via a committed `podman/nginx.conf`, and serves `/static/*` directly from a `static-data` named volume. A one-shot `static-sync` service populates that volume from the already-built image's baked-in `/app/staticfiles` on every `prod.sh` run.

**Tech Stack:** `nginx:1.27-alpine`, the existing `podman-compose` 1.0.6 / Podman 4.9.3 stack from the Podman infra plan, the same multi-stage `Containerfile` (`final` target, unchanged).

**Spec:** `docs/superpowers/specs/2026-09-22-nginx-load-balancing-design.md`

## Global Constraints

- **Scope, verbatim from spec:** production only (`prod.sh`/`compose.prod.yml`). `dev.sh`/`podman/compose.dev.yml` are untouched — dev keeps its single bind-mounted container.
- **No changes to:** `core/`, `templates/`, `harwat_main/`, `Containerfile`, `podman/compose.yml`, `podman/compose.dev.yml`, `dev.sh`. This spec is additive: it modifies `podman/compose.prod.yml` in place (per the spec's file-layout decision — no fourth layered compose file) and touches `prod.sh`'s compose invocations where they name the now-gone `app` service.
- **No TLS, no dynamic autoscaling (replica count fixed at 3, hand-edited), no active health checks** — verbatim from spec's Non-goals.
- Exact image pin: `nginx:1.27-alpine`.
- No automated test suite for this sub-project — same as the Podman infra plan, this is infrastructure config, not application logic. Each task has a real, runnable verification step instead.
- **Correction #1 (prod.sh currently names the service that's about to disappear):** `prod.sh`'s migrate line runs `podman-compose ... exec -T app python manage.py migrate --noinput` — `app` no longer exists once this plan lands (replaced by `app1`/`app2`/`app3`). The spec explicitly allows this ("this spec only adds to `podman/compose.prod.yml` ... and `prod.sh`'s invocation"). Task 3 repoints this at `app1` specifically — migrations only need to run once, not once per replica, and `app1` is guaranteed to exist as long as any replica does.
- **Correction #2 (static-sync needs root to write into its own fresh volume):** `static-sync` reuses the `app1`/`app2`/`app3` image, which the existing `Containerfile` switches to `USER app` (non-root) before `CMD`. The `static-data` named volume mounts onto `/shared`, a path that does not exist anywhere in that image — Podman creates it fresh at container start, owned `root:root`. A non-root `USER app` process cannot write into a root-owned, default-permission directory it didn't create. The spec's command (`cp -r /app/staticfiles/. /shared/ && echo static files synced`) would fail with `Permission denied` under the image's default user. Task 2's `static-sync` service definition adds `user: "0:0"` to override this — safe because `static-sync` is a one-shot copy step that exits immediately, never a long-running process, and it only reads files the image itself already created (owned root:root at build time, before the image's own `USER app` switch) and writes to a scratch volume nothing else needs to trust.
- **Correction #3 (documented limitation, not fixed by this plan):** `app1`/`app2`/`app3` each mount the *same* `sqlite-data` named volume at `/app/data` (mirroring the current single `app` service's mount, per the spec's "each identical ... minus `ports:`"). Three separate processes now hold Django's SQLite file open concurrently, which can raise `database is locked` under real concurrent write load — SQLite's file locking works across processes sharing a volume on the same host, but wasn't designed for 3-way concurrent writers. This is not a new problem this plan introduces so much as an existing one (SQLite already isn't wired for concurrency) made more visible by horizontal scaling. Out of scope to fix here — the real fix is the already-deferred Postgres/`DATABASE_URL` wiring noted in the Podman infra plan's README section. Task 4 extends that existing README note to mention this explicitly, rather than leaving it undocumented.
- Run every verification command from the repo root (all scripts already `cd` to their own directory internally, per the Podman infra plan's established convention — `prod.sh` already does this).

---

### Task 1: `podman/nginx.conf`

**Files:**
- Create: `podman/nginx.conf`

**Interfaces:**
- Consumes: nothing (first task, standalone file).
- Produces: the exact nginx config mounted read-only into the `nginx` service in Task 2, at `/etc/nginx/nginx.conf`. Upstream server names `app1`/`app2`/`app3` (port 8000 each) and the static alias path `/usr/share/nginx/static/` are the two values Task 2 must match exactly.

- [ ] **Step 1: Write `podman/nginx.conf`**

Create `podman/nginx.conf` (content finalized in the spec, copied verbatim):

```nginx
events {}

http {
    upstream app_backend {
        server app1:8000 max_fails=3 fail_timeout=30s;
        server app2:8000 max_fails=3 fail_timeout=30s;
        server app3:8000 max_fails=3 fail_timeout=30s;
    }

    server {
        listen 8000;

        location /static/ {
            alias /usr/share/nginx/static/;
        }

        location / {
            proxy_pass http://app_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

- [ ] **Step 2: Verify the config is syntactically valid nginx**

This doesn't need the app stack up — `app1`/`app2`/`app3` not resolving yet is fine, `nginx -t` only checks syntax, not that upstream hostnames resolve:

```bash
podman run --rm -v "$(pwd)/podman/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.27-alpine nginx -t
```

Expected: `nginx: configuration file /etc/nginx/nginx.conf test is successful`. Exit code 0. (This pulls `nginx:1.27-alpine` if not already cached — needs network on first run.)

- [ ] **Step 3: Commit**

```bash
git add podman/nginx.conf
git commit -m "Add nginx config: round-robin upstream across app1/app2/app3, static/ served directly"
```

---

### Task 2: `podman/compose.prod.yml` — replicas, nginx, static-sync

**Files:**
- Modify: `podman/compose.prod.yml`

**Interfaces:**
- Consumes: `podman/nginx.conf` (Task 1, exact path); the `final` build target from `Containerfile` (unchanged, from the Podman infra plan); the `sqlite-data` volume already defined in this file (unchanged, kept as-is on all three replicas).
- Produces: compose service names `app1`, `app2`, `app3`, `nginx`, `static-sync` and named volume `static-data` — consumed by Task 3's `prod.sh` changes (which now exec into `app1` by name) and by this task's own verification.

- [ ] **Step 1: Replace the `app` service with `app1`/`app2`/`app3`, add `nginx` and `static-sync`, add the `static-data` volume**

Current `podman/compose.prod.yml` (read it first to confirm it still matches this before editing — it should, nothing has touched it since the Podman infra plan merged):

```yaml
services:
  app:
    build:
      context: ..
      dockerfile: Containerfile
      target: final
    env_file:
      - ../.env.prod
    volumes:
      - sqlite-data:/app/data
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
      - ../podman/garage.prod.toml:/etc/garage.toml:ro
    command: ["/garage", "server"]

volumes:
  sqlite-data:
```

Replace it with:

```yaml
services:
  app1:
    build:
      context: ..
      dockerfile: Containerfile
      target: final
    env_file:
      - ../.env.prod
    volumes:
      - sqlite-data:/app/data
    depends_on:
      - postgres
      - pgbouncer
      - valkey
      - garage
    restart: unless-stopped

  app2:
    build:
      context: ..
      dockerfile: Containerfile
      target: final
    env_file:
      - ../.env.prod
    volumes:
      - sqlite-data:/app/data
    depends_on:
      - postgres
      - pgbouncer
      - valkey
      - garage
    restart: unless-stopped

  app3:
    build:
      context: ..
      dockerfile: Containerfile
      target: final
    env_file:
      - ../.env.prod
    volumes:
      - sqlite-data:/app/data
    depends_on:
      - postgres
      - pgbouncer
      - valkey
      - garage
    restart: unless-stopped

  static-sync:
    build:
      context: ..
      dockerfile: Containerfile
      target: final
    # Overrides the image's baked-in USER app (from Containerfile) — this
    # one-shot step must write into /shared, a path that doesn't exist
    # anywhere in the image, so Podman creates it fresh at container start
    # owned root:root. USER app can't write there; root can. Safe here
    # because this container runs once, copies files, and exits — never a
    # long-running process. See Global Constraints "Correction #2".
    user: "0:0"
    command: ["sh", "-c", "cp -r /app/staticfiles/. /shared/ && echo static files synced"]
    volumes:
      - static-data:/shared

  nginx:
    image: nginx:1.27-alpine
    volumes:
      - ../podman/nginx.conf:/etc/nginx/nginx.conf:ro
      - static-data:/usr/share/nginx/static:ro
    ports:
      - "8000:8000"
    depends_on:
      - app1
      - app2
      - app3
      - static-sync
    restart: unless-stopped

  garage:
    volumes:
      - ../podman/garage.prod.toml:/etc/garage.toml:ro
    command: ["/garage", "server"]

volumes:
  sqlite-data:
  static-data:
```

(`app1`/`app2`/`app3` lose the `ports:` mapping — `nginx` takes over host port `8000`, replicas are reachable only on the compose-internal network, by their service names, which is exactly what `podman/nginx.conf`'s `upstream app_backend` block already expects. `static-sync` has no `ports:`, `depends_on`, or `restart:` — it's a one-shot job, not a service that should ever be restarted in a loop.)

- [ ] **Step 2: Verify the merged compose config is valid**

```bash
DJANGO_DEBUG=False DJANGO_SECRET_KEY=test DJANGO_ALLOWED_HOSTS=localhost POSTGRES_DB=test POSTGRES_USER=test POSTGRES_PASSWORD=test GARAGE_RPC_SECRET=0000000000000000000000000000000000000000000000000000000000000000 \
  bash -c 'echo "DJANGO_DEBUG=$DJANGO_DEBUG
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS=$DJANGO_ALLOWED_HOSTS
POSTGRES_DB=$POSTGRES_DB
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GARAGE_RPC_SECRET=$GARAGE_RPC_SECRET" > .env.prod.test'
podman-compose --env-file .env.prod.test -f podman/compose.yml -f podman/compose.prod.yml config
rm -f .env.prod.test
```

Expected: prints the fully-resolved YAML with `app1`, `app2`, `app3`, `static-sync`, `nginx` all present, `nginx` showing the two volume mounts and port `8000:8000`, and the top-level `volumes:` section listing `pgdata`, `valkey-data`, `garage-data`, `garage-meta`, `sqlite-data`, `static-data`. Exit code 0. No bare `${...}` left anywhere. (Throwaway test env file, same pattern the Podman infra plan's own Task 4 Step 4 used — doesn't touch real `.env.prod`.)

- [ ] **Step 3: Commit**

```bash
git add podman/compose.prod.yml
git commit -m "Replace single app service with app1/app2/app3 + nginx + static-sync"
```

---

### Task 3: `prod.sh` — repoint migrate at `app1`, full end-to-end verification

**Files:**
- Modify: `prod.sh`

**Interfaces:**
- Consumes: `app1` (Task 2, exact service name), the compose invocation pattern already established in `prod.sh` (absolute `--env-file`, `-f podman/compose.yml -f podman/compose.prod.yml`).
- Produces: nothing consumed by later tasks — leaf script change.

- [ ] **Step 1: Repoint the migrate line at `app1`**

In `prod.sh`, find this line (currently the last line of the file):

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml exec -T app python manage.py migrate --noinput
```

Replace `exec -T app` with `exec -T app1`:

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml exec -T app1 python manage.py migrate --noinput
```

(Migrations only need to run once against the shared SQLite file, not once per replica — `app1` is as good a target as any, and is guaranteed to exist by definition.)

- [ ] **Step 2: Operational verification — full real run**

This is the real end-to-end check `config` validation in Task 2 can't provide. If `.env.prod` already exists from a prior Podman infra plan run, this reuses it (no secret rotation) — if not, `prod.sh` generates one exactly as before, nothing in this plan changes that.

```bash
./prod.sh
```

Expected: exits 0. Then:

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml ps
```

Expected: `app1`, `app2`, `app3`, `nginx`, `postgres`, `pgbouncer`, `valkey`, `garage` all show as running; `static-sync` shows exited with code 0 (not running — it's a one-shot job). If `static-sync` shows a non-zero exit, check its logs (`podman-compose ... logs static-sync`) — a permission-denied error there means Task 2's `user: "0:0"` override on `static-sync` is missing or wrong, re-check it.

- [ ] **Step 3: Load-balancing sanity check**

```bash
for i in 1 2 3 4 5 6; do curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8000/login/; done
```

Expected: six `200` lines, no errors — confirms nginx is reachable and proxying successfully to *some* healthy replica each time (this doesn't prove round-robin distribution specifically, just that the whole path works; nginx's default `upstream` algorithm is round-robin per the spec, no code change needed to get it).

- [ ] **Step 4: Static files served directly by nginx, not proxied to Django**

First, find the real built static asset path (its exact hashed/unhashed name depends on `STATIC_URL`/`STATICFILES_DIRS` — `harwat_main/settings.py` sets `STATIC_URL = 'static/'`):

```bash
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/dist/output.css
```

Expected: `200`.

Now prove it's nginx serving this directly, not proxying to a Django replica: stop all three app replicas and confirm the static asset is still reachable while the proxied path is not.

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml stop app1 app2 app3
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/dist/output.css
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login/
```

Expected: the static asset curl still returns `200` (nginx serves it from the `static-data` volume directly, no upstream needed); the `/login/` curl returns `502` (nginx has no healthy upstream left — this is expected and correct, not a bug). Bring the replicas back up:

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml start app1 app2 app3
```

- [ ] **Step 5: Single-replica-failure resilience**

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml stop app2
for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/login/; done
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml start app2
```

Expected: all six requests still return `200` (nginx's `proxy_next_upstream` default includes connection errors, so a request that would have hit the stopped `app2` transparently retries against `app1`/`app3` within the same client request — the curl caller never sees a failure). If any request returns a non-200, re-check `podman/nginx.conf`'s `upstream` block matches Task 1 exactly.

- [ ] **Step 6: Migration still works against the new target**

Already exercised by Step 2's `./prod.sh` run (which now runs `exec -T app1 ... migrate` per Step 1's change) — confirm no error was printed during that run. If you want to double check explicitly:

```bash
podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml exec -T app1 python manage.py migrate --check
```

Expected: exits 0 with no output (no unapplied migrations).

- [ ] **Step 7: Commit**

```bash
git add prod.sh
git commit -m "prod.sh: run migrate against app1 now that the app service is 3 replicas"
```

---

### Task 4: Documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new (documents the running system from Tasks 1-3).
- Produces: nothing — final, documentation-only task.

- [ ] **Step 1: Update the README's "Running with Podman" section**

Read the current `README.md` first (it has the "Running with Podman" section from the Podman infra plan, including a SQLite persistence note — don't remove it, extend it). Replace this existing paragraph:

```markdown
**Note:** the app container itself still runs against SQLite today (`harwat_main/settings.py`'s
`DATABASES` is unchanged by this sub-project) — the Postgres/PgBouncer/Valkey/Garage containers
come up and are reachable, but Django isn't wired to use them yet. That wiring is a separate,
future piece of work.
```

with:

```markdown
**Note:** the app containers still run against SQLite today (`harwat_main/settings.py`'s
`DATABASES` is unchanged by this sub-project) — the Postgres/PgBouncer/Valkey/Garage containers
come up and are reachable, but Django isn't wired to use them yet. That wiring is a separate,
future piece of work. In production this now means **three** `app1`/`app2`/`app3` replicas share
one SQLite file over a single named volume — functional, but SQLite wasn't designed for 3-way
concurrent writers, so heavy concurrent write load can surface `database is locked` errors. This
is one more reason the eventual Postgres wiring matters, not a new bug this sub-project
introduces.

Production now runs behind nginx, load-balancing across three app replicas (`app1`/`app2`/`app3`)
and serving `/static/*` directly from a shared volume instead of proxying it to Django. See
`docs/superpowers/specs/2026-09-22-nginx-load-balancing-design.md` for the full design. nginx
publishes the host port the single `app` container used to publish directly — nothing about how
you reach the stack from outside changes.
```

- [ ] **Step 2: Verify the README renders sensibly**

Re-read the full "Running with Podman" section after the edit. Confirm: it still starts with the same `./dev.sh` / `./prod.sh` code block, the build-css prerequisite note is untouched, the Garage bootstrap pointer is untouched, and the new nginx/SQLite-replica text reads as a continuation, not a contradiction, of what's already there.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document nginx load balancing and the 3-replica SQLite caveat in README"
```
