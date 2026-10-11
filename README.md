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

### Production data: PostgreSQL (1 primary + 2 replicas) and Garage

In production (`./prod.sh`) the app no longer runs on SQLite or keeps photos inside the containers:

- **Database** — PostgreSQL 17. `postgres` is the primary; the app reads and writes it through
  `pgbouncer`. `postgres-replica1` and `postgres-replica2` are read-only hot standbys that follow
  the primary by streaming replication, each on its own volume (`podman/postgres/*.sh`). They are
  copies to fall back on, not something the app reads from. Check them with:

  ```bash
  podman exec podman_postgres_1 psql -U bmn_harwat -d bmn_harwat -c "select client_addr, state from pg_stat_replication"
  ```

  Two rows in state `streaming` is healthy. **Failover is manual:** if the primary is lost, promote
  a replica (`podman exec podman_postgres-replica1_1 gosu postgres pg_ctl promote -D /var/lib/postgresql/data`)
  and point `DB_HOST` of `pgbouncer` at it. Nothing does this automatically.
- **Photos** — the Garage bucket `GARAGE_DEFAULT_BUCKET`, through `harwat_main/storage.py`. The
  bucket and the app's access key are created when Garage starts, from the key pair `prod.sh`
  generates into `.env.prod` (Garage does not print the secret to its log). Browsers get photos
  from `/media/...`, which the app serves to signed-in users only.
- **Settings** — all in `.env.prod`. `prod.sh` appends the ones a `.env.prod` from before this
  setup lacks (`DATABASE_ENGINE`, `DATABASE_URL`, `REPLIKASI_*`, `GARAGE_*`, `SQLITE_LAMA`,
  `BACKUP_DIR`) and never rewrites existing lines. **Back the file up**: it holds every secret.
- **Moving the old data** — the first `./prod.sh` with this setup copies the photos out of the
  old app containers (`migrasi/media/`) before removing them, then runs `manage.py impor_sqlite`
  (old SQLite file → PostgreSQL, only into an empty database) and `manage.py impor_media`
  (rescued photos → Garage). Both are safe to run again; they skip what is already there.

Development (`./dev.sh`, `manage.py runserver`, the tests) is unchanged: SQLite and `media/`.
PostgreSQL is only used when `DATABASE_ENGINE=postgresql`, Garage only when `GARAGE_ENDPOINT` is set.

Production now runs behind nginx, load-balancing across three app replicas (`app1`/`app2`/`app3`)
and serving `/static/*` directly from a shared volume instead of proxying it to Django. See
`docs/superpowers/specs/2026-09-22-nginx-load-balancing-design.md` for the full design. nginx
publishes the host port the single `app` container used to publish directly — nothing about how
you reach the stack from outside changes.
