# nginx Load Balancing — Design Spec

Date: 2026-09-22
Status: Approved for implementation planning

## Context

The Podman infra sub-project (`docs/superpowers/specs/2026-09-22-podman-infra-design.md`, being
implemented in parallel in `.claude/worktrees/podman-infra`) explicitly deferred a reverse
proxy/load balancer: "No TLS/reverse-proxy setup (out of scope — assumed to sit in front of this
host separately)." This spec covers that deferred piece: putting nginx in front of the Django app
to load-balance across multiple app container replicas.

Today, `podman/compose.prod.yml` runs a single `app` container (django-bolt's `runbolt` server,
already internally multi-process via `--processes N`, but that's multiple worker processes behind
ONE port in ONE container — not multiple containers). This spec adds horizontal scaling across
containers, with nginx distributing requests between them.

## Scope

This spec covers, **production only** (`prod.sh`/`compose.prod.yml`) — dev keeps its single
bind-mounted container, since scaling multiple auto-reloading dev containers has no benefit for
local development:

1. An `nginx` service in `podman/compose.prod.yml`, publishing the host port that `app` currently
   publishes directly (nginx takes over host port exposure; app replicas become internal-only).
2. Three app replicas (`app1`, `app2`, `app3`) as separate named compose services — not
   `podman-compose --scale`, whose support in the installed podman-compose 1.0.6 for reliable
   per-request DNS round-robin is unverified. Static, explicit services are simpler and don't
   depend on an uncertain compose feature.
3. nginx's `upstream` block load-balances across the three replicas (default round-robin,
   `max_fails`/`fail_timeout` for passive health checking — nginx's open-source build has no
   active health checks).
4. nginx serves `/static/*` directly from a shared volume instead of proxying static asset
   requests to an app replica.
5. A `static-sync` one-shot service that populates that shared volume from the already-built app
   image's baked-in `/app/staticfiles` (from the existing build-time `collectstatic` step —
   unchanged from the Podman infra plan's Task 2, not re-touched by this spec).

Out of scope: TLS/HTTPS termination (nginx here is plain HTTP — a TLS-terminating layer, if ever
needed, sits in front of this nginx or is added to it later as its own piece of work); dynamic/
autoscaling replica count (fixed at 3, changing it means editing compose + nginx config by hand);
active health checks (would need nginx Plus or a third-party module, not justified at this
project's scale); dev-environment load balancing (explicitly single-container, per Scope above).

## Approach: replica topology

Chosen: **three separate named compose services (`app1`/`app2`/`app3`)**, each an independent
full copy of the current `app` service definition (same image, same env, same `depends_on` on
postgres/pgbouncer/valkey/garage), differing only in their service name — nginx's `upstream`
block lists all three by their compose-network hostnames.

Rejected: `podman-compose up --scale app=3` with a single `app` service definition — would be
less duplicative config, but requires verifying podman-compose 1.0.6 actually supports `--scale`
with reliable per-replica DNS resolution for podman's network backend, which isn't confirmed.
Explicit named services are more config but zero ambiguity about what actually gets created and
how nginx reaches each one.

**File-layout decision:** all of this (nginx, `app1`/`app2`/`app3`, `static-sync`) goes directly
into `podman/compose.prod.yml` — modifying it, not adding a fourth layered compose file. This
sub-project is prod-only by scope (see Scope above), and `compose.prod.yml` is already the
prod-specific override file in the established `compose.yml` (base) + `compose.dev.yml` +
`compose.prod.yml` layering from the Podman infra plan; a separate `compose.nginx.yml` would add
a fourth file for content that's exclusively prod-scoped anyway, with no dev/prod split to
justify its own layer.

## nginx service

- Image: `nginx:1.27-alpine`.
- Publishes the host port `compose.prod.yml`'s `app` service currently publishes (`8000:8000` in
  the existing plan) — nginx takes this over. `app1`/`app2`/`app3` no longer publish any host
  port; they're reachable only on the compose-internal network, from nginx.
- Mounts: `podman/nginx.conf` (committed, read-only) at `/etc/nginx/nginx.conf`; the shared
  `static-data` named volume (read-only) at the path nginx serves `/static/` from.
- `depends_on`: `app1`, `app2`, `app3`, `static-sync`.

`podman/nginx.conf` (exact shape, values finalized at plan time):

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

## Static file sharing

`static-sync` service: same built image as `app1`/`app2`/`app3` (`podman/compose.prod.yml`'s
`app` build, reused), overridden `command` that copies the image's baked-in
`/app/staticfiles/` into a shared named volume and exits:

```
command: ["sh", "-c", "cp -r /app/staticfiles/. /shared/ && echo static files synced"]
```

Mounts the `static-data` named volume (read-write) at `/shared`. This container runs once per
`prod.sh` invocation and exits — it's not a long-running service, just a copy step. `nginx`
depends on it starting, not strictly on its completion (podman-compose 1.0.6's `depends_on`
completion-condition support is unverified) — in the worst case nginx serves 404s for `/static/*`
for the few seconds before `static-sync` finishes copying, then self-heals with no restart needed
(nginx reads from disk per-request, no caching of "file not found").

## Replica service definition

`app1`, `app2`, `app3` are each identical to `compose.prod.yml`'s current `app` service, minus
the `ports:` mapping (which moves to `nginx`). Same `build`, `env_file: .env.prod`,
`depends_on: [postgres, pgbouncer, valkey, garage]`, `restart: unless-stopped`.

## Testing / verification

Like the Podman infra spec, this is infrastructure config — no automated test suite. Verification
is operational:
- `podman-compose -f podman/compose.yml -f podman/compose.prod.yml config` validates syntax
  without pulling images (no new compose file — see the file-layout decision below).
- After `prod.sh` brings the stack up: `curl` the nginx-published port's `/login/` path repeatedly
  and confirm varying `Server` timing / no errors across requests (informal LB sanity check);
  `podman-compose ... ps` shows `app1`, `app2`, `app3`, `nginx`, `static-sync` (the last one
  exited 0, not running); a static asset URL (e.g. `/static/dist/output.css` — exact path depends
  on Django's `STATIC_URL`) returns 200 directly from nginx, not proxied.
- Killing one replica (`podman stop app2`) and re-curling `/login/` repeatedly still succeeds
  (nginx routes around the failed upstream after `max_fails`/`fail_timeout`).

## Non-goals (explicit)

- No TLS/HTTPS.
- No dynamic autoscaling — replica count is fixed at 3 in compose, changed by hand.
- No active health checks.
- No dev-environment changes — `dev.sh`/`compose.dev.yml` untouched.
- No changes to `core/`, `templates/`, `harwat_main/`, or the existing Podman infra plan's files
  (`Containerfile`, `podman/compose.yml`, `podman/compose.dev.yml`, `dev.sh`) — additive only,
  this spec only adds to `podman/compose.prod.yml` (or a new override file layered on top of it,
  decided at plan time) and `prod.sh`'s invocation.
