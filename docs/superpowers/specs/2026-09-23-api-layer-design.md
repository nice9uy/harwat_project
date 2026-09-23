# External JSON API Layer (django-bolt) — Design Spec

Date: 2026-09-23
Status: Approved for implementation planning

## Context

The app is 100% server-rendered Django templates + HTMX (login, dashboard, Armada CRUD) — no
JSON API exists beyond a boilerplate `GET /api/health` in `harwat_main/api.py`, auto-scaffolded
by `django-bolt` and never extended. `django-bolt` (`manage.py runbolt`, the project's server)
mounts a `BoltAPI` instance alongside normal Django views in one process
(`api.mount_django("/")`), and its `@api.*` routes are handled by a separate, Rust-compiled
router with their own request/response and auth pipeline — distinct from Django's session
middleware that the HTML views use today.

The user wants a real JSON API so external systems (a future mobile app, another service) can
integrate with this app's data, and wants the existing HTML views to stay exactly what they
already are: thin — form in, template out.

## Scope

1. JWT authentication for the API (login/refresh/logout), issued against the same Django
   `auth_user` table the browser's session login already uses — one user store, two ways in.
2. Full CRUD for `Vehicle` (list/retrieve/create/update/delete) exposed as JSON at `/api/vehicles`,
   guarded by that JWT auth.
3. A `GET /api/fleet/summary` endpoint mirroring the dashboard's fleet-summary counts.
4. Interactive API docs (OpenAPI, already built into `django-bolt`) at a fixed path, so
   "easy to integrate" is concretely true for an external developer.
5. Token revocation storage so logout / logout-all actually invalidate a refresh token, not just
   ask the client to discard it.

Out of scope (explicit):
- **No change to any existing Django view, template, or URL.** Investigated first (see Context
  above): `login_view`, `logout_view`, `dashboard_view`, and all four `fleet` views already do
  nothing but "validate a form / call the ORM once, render or redirect" — there is no buried
  business logic to extract into a shared layer for the CRUD paths. The one exception is
  `dashboard_view`'s fleet-summary aggregate query, which the API needs too (see Components).
- The browser's own HTMX-driven pages do **not** call the new API. They keep using Django's
  session-cookie auth exactly as today. The API exists for external consumers.
- No pagination, filtering, or search on `/api/vehicles` — matches the existing Armada CRUD
  spec's own non-goals (fresh, small table; add when real volume argues for it).
- No `PATCH` (partial update) — only `PUT`-style full update, matching the existing
  `VehicleForm`'s all-fields-required shape used by the HTML edit form.
- No rate limiting, no API versioning scheme (`/api/v1/...`) — nothing in this app's current
  scale justifies either yet; a single unversioned `/api/` prefix is enough to start.

## Components

### 0. One `api.py` per app, not one shared file

`django-bolt`'s `runbolt` autodiscovers a **separate `BoltAPI()` instance per Django app**: it
scans every entry in `INSTALLED_APPS` for a top-level `<app>/api.py` (or `bolt_api.py`) with a
module-level `BoltAPI()` assignment, and merges whatever it finds — this is documented in the
installed package's own `runbolt.py` (`autodiscover_apis()`), the exact same mechanism that
already picks up `harwat_main/api.py` today. It's optional per app, same as `admin.py` — `fleet`
doesn't have one yet either, `accounts` never got one built. This spec gives each app that needs
API routes its own file, matching the existing `views.py`/`urls.py`/`forms.py` per-app pattern
already used throughout this codebase, instead of piling every route into the one file that
happened to exist first:

- `harwat_main/api.py` — stays the project-level instance, keeps its existing `/api/health`
  boilerplate unchanged, gains only the OpenAPI docs config (Component 5 — a project-wide
  concern, not any one app's).
- `accounts/api.py` — **new**, its own `BoltAPI()`. Owns `/auth/login`, `/auth/refresh`,
  `/auth/logout` — accounts already owns Django auth/session concerns, this is the same domain,
  just a second door into it.
- `fleet/api.py` — **new**, its own `BoltAPI()`. Owns `/api/vehicles` and `/api/fleet/summary`.

### 1. JWT auth routes — `accounts/api.py`

`django-bolt` ships `JWTAuthViews`, a ready-made login/refresh/logout/logout-all route set
authenticating via Django's own `aauthenticate()` — but its `/auth/login` response puts the
token pair **only** in HTTP-only cookies (`{"ok": true}` is the entire JSON body). That fits a
same-origin browser JS client, not the external/mobile audience this spec targets, which needs
the access and refresh tokens **in the response body** to store and send back as
`Authorization: Bearer <token>` on every request (cookies don't travel the same way from a
mobile HTTP client or a server-to-server integration).

So this spec does **not** call `JWTAuthViews(...).register(api)` — it writes three small routes
on `accounts/api.py`'s own `BoltAPI()` instance, using the same underlying primitives
`JWTAuthViews` itself uses, but returning tokens in the body:

```python
from django.contrib.auth import aauthenticate
from django_bolt import BoltAPI
from django_bolt.auth import (
    JWTAuthentication, LoginCredentials, create_token_pair,
    rotate_refresh_token, TokenRotationError,
)
from django_bolt.exceptions import HTTPException

api = BoltAPI()

refresh_auth = JWTAuthentication(secret=settings.SECRET_KEY, cookie=None, token_type="refresh")

@api.post("/auth/login", tags=["auth"])
async def login(request, credentials: LoginCredentials):
    user = await aauthenticate(username=credentials.username, password=credentials.password)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    pair = create_token_pair(user, secret=settings.SECRET_KEY, method="pwd")
    return {"access_token": pair.access, "refresh_token": pair.refresh, "token_type": "bearer"}

@api.post("/auth/refresh", auth=[refresh_auth], tags=["auth"])
async def refresh(request):
    try:
        pair = await rotate_refresh_token(
            request["context"]["auth_claims"], store=revocation_store, secret=settings.SECRET_KEY,
        )
    except TokenRotationError:
        raise HTTPException(status_code=401, detail="Invalid or reused refresh token")
    return {"access_token": pair.access, "refresh_token": pair.refresh, "token_type": "bearer"}

@api.post("/auth/logout", auth=[refresh_auth], tags=["auth"])
async def logout(request):
    claims = request["context"]["auth_claims"]
    await revocation_store.revoke(claims["jti"], exp=claims.get("exp"))
    return {"detail": "Logged out"}
```

(Exact parameter names/shapes — `TokenPair.access` vs `.access_token`, `create_token_pair`'s
full signature, `LoginCredentials`'s fields — get confirmed against the installed
`django_bolt` source during implementation, the way this codebase already treats third-party
APIs: read the installed package, don't guess. This block is the shape, not a copy-paste
guarantee.)

`refresh` and `logout` require a valid **refresh** token (`token_type="refresh"`); `/api/vehicles`
and `/api/fleet/summary` require a valid **access** token — two separately-configured
`JWTAuthentication` instances, both reading `Authorization: Bearer <token>` (the default
`header="authorization"` source — no `cookie=` override), both keyed off `settings.SECRET_KEY`
(reusing Django's existing secret — no new secret to provision or rotate separately).

### 2. Token revocation — `accounts/models.py`

New model (`accounts` currently has no `models.py` at all — this is its first, and it's
auth-adjacent, not a `fleet` concern):

```python
class RevokedToken(models.Model):
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
```

Wired via `django_bolt.auth.DjangoORMRevocation(model="accounts.RevokedToken")`. Chosen over
`DjangoCacheRevocation` because Django's `CACHES` isn't configured against Valkey anywhere in
this project yet (the Valkey container runs, but nothing points Django's cache framework at it)
— wiring that up is a separate, unrelated infra task, not something this API-layer spec should
smuggle in. `DjangoORMRevocation` needs zero new infra, just this one model + migration.
`InMemoryRevocation` was rejected: `runbolt --processes N` in prod runs multiple worker
processes, so an in-memory store wouldn't be shared between them — a token revoked against one
worker would still work against another.

No scheduled cleanup task for expired `RevokedToken` rows in this spec (the library's own docs
call this out as a follow-up concern, e.g. a cron/celery job) — out of scope, table grows slowly
(one row per logout) and isn't a correctness problem, just eventual housekeeping.

### 3. Vehicle CRUD API — `fleet/api.py`

A `ViewSet` (django-bolt's higher-level CRUD abstraction — list/retrieve/create/update/destroy
generated from a `queryset` + serializer, the library's idiomatic tool for exactly this shape of
resource, not hand-written `@api.get/post/put/delete` per action):

```python
from django_bolt import BoltAPI
from django_bolt.views import ViewSet
from django_bolt.serializers import Serializer
from django_bolt.auth import JWTAuthentication, IsAuthenticated

from .models import Vehicle

api = BoltAPI()

class VehicleSerializer(Serializer):
    id: int = field(read_only=True)
    nopol: str
    jenis: str
    merek: str
    tahun: int
    status: str
    odometer_km: int
    penanggung_jawab: str

access_auth = JWTAuthentication(secret=settings.SECRET_KEY)

@api.viewset("/api/vehicles")
class VehicleViewSet(ViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    auth = [access_auth]
    guards = [IsAuthenticated()]
```

`jenis`/`status` stay plain `str` on the wire (not a msgspec enum) — external clients send/receive
the same choice values (`"truk"`, `"siap_pakai"`, etc.) already used internally; Django's own
`choices=` validation on the model fields still rejects an invalid value on save (a `ValidationError`
that `django-bolt`'s error handling turns into a structured 4xx — exact status/shape confirmed
against the installed error-handling code during implementation, not guessed here).
Uniqueness on `nopol` is already enforced at the model layer (`unique=True`) — the same
constraint the HTML form relies on, hit through a different door.

### 4. Fleet summary — `fleet/services.py` (new) + `accounts/views.py` (modified)

The one genuine duplication risk: `dashboard_view`'s fleet-summary aggregate needs to be
computed identically whether the caller is the dashboard template or `GET /api/fleet/summary`.
Extract it:

```python
# fleet/services.py
from django.db.models import Count
from .models import Vehicle

def get_fleet_summary() -> dict:
    status_counts = dict(Vehicle.objects.values_list("status").annotate(count=Count("id")))
    return {
        "total": sum(status_counts.values()),
        "ready": status_counts.get(Vehicle.Status.SIAP_PAKAI, 0),
        "in_repair": status_counts.get(Vehicle.Status.DALAM_PERBAIKAN, 0),
        "due_soon": status_counts.get(Vehicle.Status.PERLU_SERVIS, 0),
    }
```

`accounts/views.py::dashboard_view` calls this instead of inlining the query — behavior
identical, output identical, `accounts/tests.py`'s existing
`test_dashboard_shows_real_fleet_summary_counts` still passes unmodified. New route:

```python
# fleet/api.py
@api.get("/api/fleet/summary", auth=[access_auth], guards=[IsAuthenticated()])
async def fleet_summary(request):
    from asgiref.sync import sync_to_async
    return await sync_to_async(get_fleet_summary)()
```

(`sync_to_async` because `get_fleet_summary()` does a synchronous ORM query inside an `async def`
handler — the same bridge `django-bolt` itself uses internally, per its `concurrency.py`
helpers seen in the installed package; implementation confirms the idiomatic call against
that module rather than hand-rolling a thread bridge.)

### 5. API docs — `harwat_main/api.py`

`django-bolt` ships OpenAPI schema generation plus Swagger/Redoc/Scalar/Stoplight/Rapidoc render
plugins built in (`django_bolt.openapi`). Enable one (Scalar — modern, no extra config beyond
picking it) at a fixed path, e.g. `/api/docs`, via `BoltAPI`'s own `OpenAPIConfig` /
`ScalarRenderPlugin`, configured on `harwat_main/api.py`'s instance — the project-level file,
since the docs page is expected to aggregate routes from every app's `BoltAPI()` instance
(`accounts/api.py`, `fleet/api.py`) once `runbolt` merges them, not just its own `/api/health`.
Whether that aggregation is automatic or needs an explicit step is confirmed against the
installed `openapi`/`runbolt` code during implementation — exact wiring not guessed here. This
is what makes "gampang diintegrasikan" concretely true: an external developer gets a live,
try-it-out API reference for free, no separate docs to hand-write or maintain.

## Error handling

`django-bolt` already formats exceptions as structured JSON (`{"detail": ...}` for
`HTTPException`, a validation-error shape for `RequestValidationError` — seen directly in the
installed `error_handlers.py`). This spec doesn't add custom exception handling — it relies on
that existing behavior for: invalid login credentials (401), missing/expired/revoked token (401),
a `Vehicle` that fails model validation on create/update (4xx via Django's own `ValidationError`
path), and a nonexistent `pk` on retrieve/update/delete (404, `ViewSet`'s built-in `get_object`
behavior per its docstring).

## Testing

`django_bolt.testing` exists in the installed package (confirmed present, not yet inspected in
depth) — the implementation plan uses it (matching this codebase's existing convention of using
the framework's own supported test tooling rather than raw `httpx` calls) to write:

- Login: valid credentials → 200 + both tokens in the body; invalid credentials → 401.
- Refresh: valid refresh token → new pair; a token already revoked (post-logout) → 401.
- Logout: revokes the refresh token; using it again on `/auth/refresh` afterward → 401.
- Vehicle API: unauthenticated request → 401 on every route; authenticated CRUD round-trip
  (create → appears in list → retrieve by id → update persists → delete removes it); duplicate
  `nopol` on create → 4xx, no row created (mirrors `fleet/tests.py`'s existing
  `test_post_duplicate_nopol_reshows_form_with_error`, same constraint, different door).
- `GET /api/fleet/summary` matches `get_fleet_summary()`'s output for a seeded set of vehicles
  (mirrors `accounts/tests.py`'s existing dashboard-summary test, same function, two callers).
- Existing Django-view test suite (`accounts/tests.py`, `fleet/tests.py`) stays green
  unmodified — this spec asserts zero behavior change there, so the existing 38 tests passing
  after implementation is itself a spec-compliance check, not just incidental.

## Non-goals (explicit)

- Browser/HTMX pages calling the new API — out of scope per Scope section above.
- Pagination, filtering, search, `PATCH`, rate limiting, API versioning — all explicitly deferred,
  matching this app's current scale and the existing Armada CRUD spec's own precedent for what
  "not yet" looks like.
- Scheduled cleanup of expired `RevokedToken` rows — a follow-up housekeeping task, not a
  correctness requirement for this spec.
- Wiring Django's `CACHES` to Valkey — a separate, unrelated infra task; this spec uses
  `DjangoORMRevocation` specifically to avoid needing it.
