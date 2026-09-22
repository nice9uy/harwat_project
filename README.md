# BMN Harwat

Vehicle maintenance / fleet management app.

## Development setup

```bash
uv sync
./scripts/build-css.sh   # required before first run, and again after any template or Tailwind change
uv run python manage.py migrate
uv run python manage.py runserver
```

## Running with Podman

The full stack (app, PostgreSQL+PgBouncer, Valkey, Garage) runs under Podman via
`podman-compose`. See `docs/superpowers/specs/2026-09-22-podman-infra-design.md` for the full
design.

**Prerequisite:** the container image's `collectstatic` step needs `static/dist/output.css` to
exist (see "Development setup" above) — with Django's default staticfiles storage, `collectstatic`
does *not* fail if this file is missing, it just silently ships a visually broken app. Both
scripts below now run `./scripts/build-css.sh` automatically if `static/dist/output.css` isn't
already present, so this is handled for you — mentioned here so anyone reading `dev.sh`/`prod.sh`
knows why that guard is there.

```bash
./dev.sh    # local dev: bind-mounted code, auto-reload, DEBUG on
./prod.sh   # production: built image, multi-process, secrets auto-generated into .env.prod on first run
```

Production also needs a one-time manual Garage cluster bootstrap after the first `./prod.sh` —
see `docs/podman-garage-prod-setup.md`.

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
