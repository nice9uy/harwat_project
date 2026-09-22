# BMN Harwat

Vehicle maintenance / fleet management app.

## Development setup

```bash
uv sync
./scripts/build-css.sh   # required before first run, and again after any template or Tailwind change
uv run python manage.py migrate
uv run python manage.py runserver
```
