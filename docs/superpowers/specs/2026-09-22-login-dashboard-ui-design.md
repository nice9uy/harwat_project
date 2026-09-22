# Login + Dashboard UI — Design Spec

Date: 2026-09-22
Status: Approved for implementation planning

## Context

`bmn_harwat` is a vehicle maintenance/fleet management app for a Ministry-of-Defense-style
organization ("BMN Harwat" — pemeliharaan dan perawatan kendaraan). The repo currently is a
bare Django 6.1 scaffold: `harwat_main/` project package (settings/urls/wsgi/asgi), `manage.py`,
and `pyproject.toml` declaring `django-bolt>=0.11.1` (already in `INSTALLED_APPS` as
`django_bolt`). No custom app, no models, DB is still the default sqlite.

The eventual target stack is broader: Podman, django-bolt (fullstack routing), Valkey (cache),
PostgreSQL + PgBouncer, Garage (S3-compatible storage), Tailwind CSS + Alpine.js + HTMX. That
full stack is **out of scope for this spec** — it bundles infrastructure concerns that don't
block UI work and deserve their own design/plan cycle once there's a reason to deploy (real
models, real auth needs beyond Django's built-in session auth, file uploads that need object
storage, etc.).

## Scope

This spec covers only:
1. Frontend tooling setup (Tailwind CLI, vendored Alpine.js/HTMX) — no CDN dependency.
2. A `core` Django app with a login page and a dashboard page.
3. Auth flow using Django's built-in `django.contrib.auth`, HTMX-submitted login form.
4. Dashboard page with four mock-data content blocks, gated behind login.
5. View-level tests for the auth gate and login flow.

Out of scope (separate future sub-projects): Podman/container setup, PostgreSQL + PgBouncer,
Valkey, Garage, real fleet/vehicle models, forgot-password email flow, role-based access
control, 2FA.

## Visual identity

"Elegant Ministry of Defense, not overtly military" — no camo/olive-drab, no stencil fonts, no
military iconography (stars, chevrons, rank insignia). Instead: a formal, trustworthy,
institutional feel via color and restraint.

- **Primary (navy):** `#0B1F3A` (near-black navy, page chrome / sidebar background)
- **Secondary (navy, lighter):** `#132C4F` (cards, elevated surfaces on navy)
- **Accent (muted gold):** `#C9A227` (used sparingly — active nav item, primary buttons, focus
  rings, small highlights only; never as a large fill)
- **Neutral surfaces:** white / slate-50 for main content background (not navy — navy is chrome,
  not canvas), slate grays for body text and borders
- **Status colors:** standard semantic (red for overdue/alerts, amber for "due soon", green for
  "ready/ok") — kept separate from the gold accent so alerts stay legible

Typography: a clean, professional sans-serif (system font stack via Tailwind defaults is fine —
no custom webfont needed for this phase). Generous whitespace, subtle borders/shadows over heavy
borders, rounded-md corners (not sharp, not pill-shaped) — reads as "modern institutional
software," not a government form from 1998 and not a startup dashboard.

These are defined as Tailwind theme tokens (`tailwind.config.js` `theme.extend.colors`), not
hardcoded hex values scattered through templates.

## Approach: frontend tooling

Chosen: **Tailwind standalone CLI binary (no Node/npm) + Alpine.js and HTMX vendored as local
static files** (not CDN).

Rationale:
- No CDN calls fits the institutional/defense-adjacent theme (no external asset dependency,
  works in restricted/offline network contexts later).
- Standalone Tailwind CLI is a single binary — no Node toolchain added to what is otherwise a
  pure-Python project, and it containerizes cleanly later (Podman multi-stage build can run the
  binary in a build stage without needing a Node base image).
- Tailwind's Play CDN (the zero-setup alternative) is explicitly not recommended for anything
  beyond a quick demo per Tailwind's own docs.

Rejected: Play CDN (not production-appropriate, external dependency); full Node/PostCSS pipeline
(adds a toolchain this project doesn't otherwise need).

## App structure

New Django app: `core` (not split into `accounts` + `dashboard` yet — there are no models and no
independent lifecycle for auth vs. dashboard code yet; splitting now would be premature
structure with nothing to bound). Layout:

```
core/
  views.py          # login_view (or LoginView subclass), dashboard_view
  urls.py
  forms.py          # AuthenticationForm subclass with Tailwind-classed widgets
  tests.py
templates/
  base.html          # shared shell: sidebar + topbar, navy/gold theme
  core/
    login.html       # standalone (no sidebar), centered card
    dashboard.html    # extends base.html
static/
  src/input.css       # Tailwind source (@tailwind directives + any custom layer)
  dist/output.css      # compiled output (build artifact, gitignored)
  vendor/
    htmx.min.js
    alpinejs.min.js
tailwind.config.js
```

## Layout

Dashboard: fixed left sidebar (logo/org name, nav links: Dashboard, Armada, Jadwal, Servis,
Laporan — links can be non-functional placeholders for now except Dashboard) + topbar (page
title, user menu). Main content area (white/slate-50 background) holds the four dashboard
blocks. Login page: standalone centered card on a navy background, no sidebar/topbar.

## Auth flow

- Use `django.contrib.auth.views.LoginView` behavior via a custom view (or subclass) so Django's
  session auth, `next` redirect handling, and password validators are reused as-is — no custom
  auth backend needed.
- Custom `AuthenticationForm` subclass sets `widget.attrs['class']` to the Tailwind input classes
  in `__init__`, so templates can just render `{{ form.username }}` / `{{ form.password }}`
  without manual `<input>` reconstruction.
- Form fields: username, password, "ingat saya" (remember-me) checkbox that adjusts session
  expiry (`request.session.set_expiry(0)` vs. a longer expiry — standard Django pattern, not a
  new mechanism), "lupa password?" link pointing to a placeholder URL name
  (`core:password_reset_placeholder` or similar) — the view for that link renders a small "belum
  tersedia, hubungi admin" notice page for now; the real reset-email flow is a future sub-project.
- Submission is via HTMX (`hx-post` on the form, `hx-target` swaps in validation errors without a
  full page reload; a successful login does a full redirect to `/dashboard/` via
  `HX-Redirect` response header, which is the standard HTMX pattern for post-login navigation).
- `dashboard_view` (and any future `core` views) are gated with `@login_required` using Django's
  default `LOGIN_URL` pointing at the login route.

## Dashboard content (mock data)

`dashboard_view` builds its context from plain Python data structures (no DB query) shaped like
what the eventual models will look like, so swapping to real queries later is a small diff, not a
template rewrite. Four blocks:

1. **Ringkasan armada** — stat cards: total kendaraan, siap pakai, dalam perbaikan, butuh servis
   segera (counts).
2. **Jadwal perawatan mendatang** — table: kendaraan, jenis servis, tanggal jadwal (next ~7-14
   days), status.
3. **Alert overdue** — list, visually distinct (red/amber), kendaraan yang lewat jadwal servis.
4. **Aktivitas terbaru** — short log: siapa, aksi, kapan (e.g. "Budi menyelesaikan servis rutin —
   2 jam lalu").

Single generic user role for this phase — no per-role view variation. RBAC is future scope.

## Testing

View-level tests via Django's test client, in `core/tests.py`:
- `/dashboard/` redirects to login when not authenticated.
- `/dashboard/` returns 200 and renders the four content blocks when authenticated.
- Valid login (`POST /login/`) authenticates and redirects to `/dashboard/`.
- Invalid login shows a form error and does not authenticate.

No unit tests needed for the mock dashboard data itself (it's static Python data, not logic).

## Non-goals (explicit)

- No Podman/container files in this pass.
- No PostgreSQL/PgBouncer/Valkey/Garage wiring — DB stays sqlite, cache stays Django's default
  (locmem or none), no object storage integration.
- No real vehicle/fleet models — dashboard data is mock.
- No working forgot-password email flow, no 2FA, no RBAC.
