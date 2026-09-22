# Armada (Vehicle Fleet) CRUD — Design Spec

Date: 2026-09-22
Status: Approved for implementation planning

## Context

The dashboard (`accounts` app, see `docs/superpowers/specs/2026-09-22-login-dashboard-ui-design.md`)
ships a sidebar with four nav items — Armada, Jadwal, Servis, Laporan — all currently `href="#"`
placeholders. The dashboard's `fleet_summary` block also shows hardcoded numbers (total,
ready, in_repair, due_soon). There are no models anywhere in the project yet — no
`models.py` in any app, default sqlite DB has no application tables.

This spec covers wiring up the first of those four menu items: **Armada**, a CRUD table of the
vehicle fleet. Jadwal (schedule), Servis (service history), and Laporan (reports) are each
their own future sub-project — out of scope here, their nav links stay `href="#"` until their
turn.

## Scope

1. New Django app `fleet`, holding a `Vehicle` model.
2. Full CRUD (list, create, update, delete) for `Vehicle`, function-based views mirroring the
   style already established in `accounts/views.py`.
3. Sidebar "Armada" link in `templates/base.html` wired to the real list view.
4. Dashboard's `fleet_summary` block recomputed from real `Vehicle` data instead of the
   hardcoded dict.
5. View-level tests mirroring `accounts/tests.py` conventions.

Out of scope: Jadwal/Servis/Laporan (separate future specs), role-based permissions beyond
`@login_required` (single implicit role today, same as the rest of the app), soft-delete /
audit trail, vehicle photo upload (no object storage wired to any model yet), bulk
import/export, pagination (deferred until real data volume argues for it — YAGNI for a
freshly-empty table), dark mode (separate, already-scoped, unrelated piece of work — will be
applied as its own pass across all pages including these new ones once it lands).

## Data model

New file `fleet/models.py`:

```python
class Vehicle(models.Model):
    class Jenis(models.TextChoices):
        TRUK = "truk", "Truk"
        JEEP = "jeep", "Jeep"
        MOTOR = "motor", "Motor"
        AMBULANS = "ambulans", "Ambulans"
        MOBIL = "mobil", "Mobil"
        LAINNYA = "lainnya", "Lainnya"

    class Status(models.TextChoices):
        SIAP_PAKAI = "siap_pakai", "Siap Pakai"
        DALAM_PERBAIKAN = "dalam_perbaikan", "Dalam Perbaikan"
        PERLU_SERVIS = "perlu_servis", "Perlu Servis"

    nopol = models.CharField(max_length=20, unique=True, verbose_name="Nomor Polisi")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    merek = models.CharField(max_length=100, verbose_name="Merek/Model")
    tahun = models.PositiveSmallIntegerField(verbose_name="Tahun")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SIAP_PAKAI)
    odometer_km = models.PositiveIntegerField(default=0, verbose_name="Odometer (KM)")
    penanggung_jawab = models.CharField(max_length=150, verbose_name="Penanggung Jawab")

    class Meta:
        ordering = ["nopol"]

    def __str__(self):
        return self.nopol
```

`nopol` unique — it's the real-world identifier for a vehicle, duplicate entries would be a data
error, not a valid case. No `created_at`/`updated_at` — nothing in scope needs them (list is
sorted by `nopol`, not recency), and default ordering already gives a stable table order without
them; add later if a real need shows up.

Choices are a closed set here because both fields feed the dashboard's status breakdown and any
future Laporan aggregation — free text would make that unreliable. `tahun` as a plain
`PositiveSmallIntegerField` (not a `DateField`) — a vehicle production year, not a calendar date.

Migration: standard `makemigrations fleet` — first migration for this app, no data migration
needed (fresh table, nothing to backfill).

## Views and URLs

New file `fleet/urls.py`, `app_name = "fleet"`, mounted at `/armada/` in `harwat_main/urls.py`
(`path('armada/', include('fleet.urls'))`, alongside the existing `path('', include('accounts.urls'))`).

Function-based views in `fleet/views.py`, all `@login_required` (matches `dashboard_view`'s
existing gate — there's one implicit role in this app today, no per-view permission split):

| URL | View | Behavior |
|---|---|---|
| `armada/` | `vehicle_list` | Table of all vehicles, ordered by `nopol` (model default) |
| `armada/tambah/` | `vehicle_create` | GET renders empty form; POST validates + creates, redirects to list |
| `armada/<int:pk>/edit/` | `vehicle_update` | GET renders form pre-filled from `get_object_or_404`; POST validates + saves, redirects to list |
| `armada/<int:pk>/hapus/` | `vehicle_delete` | `@require_POST` only (mirrors `logout_view`'s pattern) — deletes, redirects to list. No separate confirm page; the list template's delete button is a small POST form with a JS `confirm()`, same weight as this app's other destructive action (logout doesn't even confirm, but delete is more consequential, so it gets one). |

`vehicle_create` and `vehicle_update` share one template (`fleet/vehicle_form.html`) and one
`ModelForm` (`fleet/forms.py::VehicleForm`) — same create/edit pattern, no reason to duplicate
the form markup.

## Forms

`fleet/forms.py`:

```python
class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["nopol", "jenis", "merek", "tahun", "status", "odometer_km", "penanggung_jawab"]
```

Widget styling applied in `__init__`, matching `accounts/forms.py::LoginForm`'s existing pattern
— shared `TEXT_INPUT_CLASSES`/`SELECT_CLASSES` constants (new module-level constants in
`fleet/forms.py`, same Tailwind utility string style as `accounts/forms.py`, not re-imported from
there — the two forms modules don't otherwise depend on each other and duplicating one class
string is cheaper than introducing a cross-app import for it).

## Templates

New `templates/fleet/` directory (mirrors `templates/accounts/`):

- `vehicle_list.html` — extends `base.html`. Table columns: Nopol, Jenis, Merek, Tahun, Status
  (as a colored badge — reuse the same red/amber/green semantic colors the spec for the
  dashboard already established), Odometer, Penanggung Jawab, Aksi (Edit/Hapus links+form).
  "+ Tambah Kendaraan" button above the table linking to `vehicle_create`. Empty state
  ("Belum ada data kendaraan.") for the zero-rows case, since the table starts genuinely empty.
- `vehicle_form.html` — extends `base.html`. Same form-field markup pattern as
  `templates/accounts/login.html` (label + input + error display per field), title switches
  between "Tambah Kendaraan" / "Edit Kendaraan" based on whether the view passed an existing
  instance.

`templates/base.html` change: sidebar's Armada link

```html
<a href="#" ...>Armada</a>
```

becomes

```html
<a href="{% url 'fleet:vehicle_list' %}" ...>Armada</a>
```

(Jadwal/Servis/Laporan links stay `href="#"` — untouched, out of scope.)

## Dashboard integration

`accounts/views.py::dashboard_view`'s `fleet_summary` dict changes from hardcoded values to:

```python
from fleet.models import Vehicle

vehicle_counts = Vehicle.objects.values("status").annotate(count=Count("id"))
# folded into the same {"total", "ready", "in_repair", "due_soon"} shape the template
# already consumes — template (templates/accounts/dashboard.html) is unchanged
```

`upcoming_maintenance` and `overdue_alerts` stay hardcoded dicts — they're Jadwal/Servis domain
data with no backing model yet; wiring them is that future spec's job, not this one's.

This does introduce a cross-app import (`accounts/views.py` importing from `fleet.models`).
That's an accepted, ordinary Django pattern (one app's view reading another app's model) — not
a layering violation worth avoiding here, since `accounts` already owns the dashboard page and
that page's job is exactly to summarize other apps' data.

## Testing

New `fleet/tests.py`, mirroring `accounts/tests.py`'s style (`django.test.TestCase`,
`self.client`, a logged-in-user fixture in `setUp`):

- Anonymous access to any of the 4 URLs redirects to login (same pattern as
  `accounts/tests.py`'s existing dashboard-requires-login test).
- `vehicle_list` renders created `Vehicle` rows.
- `vehicle_create` POST with valid data creates a row and redirects; invalid data
  (missing required field) re-renders the form with errors, no row created.
- `vehicle_update` POST changes an existing row's fields.
- `vehicle_delete` POST removes the row; GET on the delete URL is rejected (405, from
  `@require_POST`).
- Dashboard test (extends existing `accounts/tests.py` dashboard test) asserts
  `fleet_summary["total"]` reflects actual `Vehicle.objects.count()` given a couple of seeded
  rows, not the old hardcoded `42`.

## Non-goals (explicit)

- Pagination, search/filter, sorting controls on the table — YAGNI until real data volume
  justifies it.
- Any role/permission model beyond "logged in or not."
- Soft delete / audit history of changes.
- Vehicle photo/document upload (no object storage wired to any model yet — Garage exists at
  the infra layer per the Podman infra spec, but nothing in the app talks to it).
- API endpoints (JSON) — server-rendered HTML only, matching the rest of the app today.
