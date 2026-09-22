# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:${PATH}"

COPY . .


FROM python:3.14-slim AS final

RUN groupadd --system app && useradd --system --gid app --home /app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:${PATH}"

RUN python manage.py collectstatic --noinput

# db.sqlite3 (BASE_DIR / 'db.sqlite3', i.e. /app/db.sqlite3) needs to survive
# rebuilds in prod. Podman can't mount a named volume directly onto a single
# file path (it either creates an empty directory there if nothing pre-exists,
# or hard-fails to mount if a file does) — so the volume backs the directory
# /app/data instead, and db.sqlite3 is a symlink into it. Persistence is wired
# up in podman/compose.prod.yml's `sqlite-data:/app/data` volume mount.
RUN mkdir -p /app/data && chown app:app /app/data \
    && ln -s data/db.sqlite3 db.sqlite3 && chown -h app:app db.sqlite3

USER app

EXPOSE 8000

CMD ["python", "manage.py", "runbolt", "--host", "0.0.0.0", "--port", "8000", "--processes", "4", "--respawn-failed-workers"]
