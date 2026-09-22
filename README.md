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
