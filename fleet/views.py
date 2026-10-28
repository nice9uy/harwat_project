from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from django.utils.text import slugify

from accounts.paging import halaman

from .forms import VehicleForm
from .models import Vehicle
from .qr import qr_png_with_logo


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _htmx_redirect(url):
    response = HttpResponse(status=204)
    response["HX-Redirect"] = url
    return response


def _group(request):
    # Which Armada tab the request belongs to (?group=B); unknown or missing
    # values fall back to the default group.
    group = request.GET.get("group", "")
    return group if group in Vehicle.GroupKendaraan.values else Vehicle.GroupKendaraan.GOLONGAN_B


def _matra(request):
    """The matra a vehicle is added for: the one a superadmin picked on Form
    Tambah (?matra=), anyone else's own; "" when there is none."""
    from accounts import roles  # accounts imports fleet models

    if not request.user.is_superuser:
        return getattr(getattr(request.user, "publik", None), "matra", "")
    matra = request.GET.get("matra", "")
    return matra if matra in dict(roles.MATRA) else ""


def _list_url(group):
    """Armada list on the given group's tab (the default tab needs no query)."""
    url = reverse("fleet:vehicle_list")
    return url if group == Vehicle.GroupKendaraan.GOLONGAN_B else f"{url}?{urlencode({'group': group})}"


@login_required
def vehicle_list(request):
    group = _group(request)
    vehicles = Vehicle.objects.filter(group_kendaraan=group).prefetch_related("fotos").order_by("nopol", "id")
    return render(request, "fleet/vehicle_list.html", {
        "vehicles": halaman(request, vehicles),
        "group": group,
        "groups": Vehicle.GroupKendaraan.choices,
    })


def _next_url(request):
    """Safe same-site ?next= to return to after saving (e.g. Form Tambah)."""
    url = request.GET.get("next", "")
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return None


@login_required
def vehicle_create(request):
    from accounts import roles, status
    from accounts.models import Laporan, PekerjaanAktif  # accounts imports fleet models

    # Form Group may keep a Tim Penambahan Data member off some vehicle groups.
    if _group(request) not in roles.form_tambah_boleh(request.user):
        if _is_htmx(request):
            # Say so in the modal: a bare 403 leaves HTMX showing nothing, as
            # if Simpan did nothing (the access may be taken away while the
            # form is open).
            return render(request, "fleet/_vehicle_form_terlarang.html", {
                "label": dict(roles.FORM_TAMBAH)[_group(request)],
            })
        return HttpResponse(status=403)
    next_url = _next_url(request)
    pakai_biodata = bool(request.GET.get("penambah"))
    laporan_penambah = None
    if pakai_biodata:
        laporan_penambah = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        form.instance.group_kendaraan = _group(request)
        form.instance.ditambahkan_oleh = request.user
        form.instance.matra = _matra(request)
        if pakai_biodata and laporan_penambah is None:
            form.add_error(None, "Isi biodata di Info Profil terlebih dahulu.")
        if form.is_valid():
            with transaction.atomic():
                if pakai_biodata and laporan_penambah:
                    form.instance.penambah = laporan_penambah
                vehicle = form.save()
            status.selesai(request.user, PekerjaanAktif.Jenis.PENAMBAHAN)
            if next_url:
                messages.success(request, f"Kendaraan {vehicle.nopol} berhasil ditambahkan.")
            target = next_url or _list_url(vehicle.group_kendaraan)
            if _is_htmx(request):
                return _htmx_redirect(target)
            return redirect(target)
    else:
        form = VehicleForm()
        if pakai_biodata:
            # Shown on the member's Status menu until the vehicle is saved or cancelled.
            status.mulai(
                request.user, PekerjaanAktif.Jenis.PENAMBAHAN,
                keterangan=dict(roles.FORM_TAMBAH)[_group(request)],
            )
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {
        "form": form, "is_edit": False, "group": _group(request), "next_url": next_url or "",
        "pakai_biodata": pakai_biodata, "matra": _matra(request),
        "matra_label": dict(roles.MATRA).get(_matra(request), ""),
    })


@login_required
def vehicle_update(request, uid):
    from accounts import roles  # accounts depends on fleet, not the other way round

    # Opened from Kendaraan (superuser) or from a report's Edit action
    # (Superuser, Admin, Ketua Tim), which comes back to it via ?next=.
    if not roles.boleh_ubah_laporan(request.user):
        return HttpResponse(status=403)
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    next_url = _next_url(request)
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            if next_url:
                messages.success(request, f"Kendaraan {vehicle.nopol} berhasil diperbarui.")
            target = next_url or _list_url(vehicle.group_kendaraan)
            if _is_htmx(request):
                return _htmx_redirect(target)
            return redirect(target)
    else:
        form = VehicleForm(instance=vehicle)
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {"form": form, "is_edit": True, "vehicle": vehicle, "next_url": next_url or ""})


@login_required
def vehicle_delete_confirm(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    return render(request, "fleet/_vehicle_delete_confirm.html", {"vehicle": vehicle})


@login_required
@require_POST
def vehicle_delete(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    from accounts.golongan import GOLONGAN  # accounts depends on fleet, not the other way round

    if any(getattr(vehicle, cfg.relasi).exists() for cfg in GOLONGAN.values()) or vehicle.servis.exists():
        messages.error(request, f"Kendaraan {vehicle.nopol} tidak bisa dihapus karena sudah punya data pemeriksaan atau servis.")
        return redirect(_list_url(vehicle.group_kendaraan))
    # Rows cascade, but the image files would otherwise stay on disk.
    for foto in vehicle.fotos.all():
        foto.image.delete(save=False)
    vehicle.delete()
    return redirect(_list_url(vehicle.group_kendaraan))


@login_required
def vehicle_qr(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    response = HttpResponse(qr_png_with_logo(vehicle.qr_text(), label=vehicle.nopol), content_type="image/png")
    response["Cache-Control"] = "private, no-cache"
    if request.GET.get("unduh"):
        response["Content-Disposition"] = f'attachment; filename="qr-{slugify(vehicle.nopol)}.png"'
    return response


@login_required
def vehicle_photos(request, uid):
    vehicle = get_object_or_404(Vehicle.objects.prefetch_related("fotos"), uuid=uid)
    return render(request, "fleet/_vehicle_photos_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_qr_modal(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    return render(request, "fleet/_vehicle_qr_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_lookup(request):
    """Vehicle details for a scanned QR code, looked up by No. Registrasi."""
    vehicle = Vehicle.objects.filter(nopol=request.GET.get("nopol", "").strip()).first()
    if vehicle is None:
        return JsonResponse({"error": "Kendaraan tidak ditemukan."}, status=404)
    return JsonResponse({
        "uuid": str(vehicle.uuid),
        "nopol": vehicle.nopol,
        "merek": vehicle.merek,
        "no_chasis": vehicle.no_chasis,
        "no_mesin": vehicle.no_mesin,
        "group_kendaraan": vehicle.get_group_kendaraan_display(),
        "group_kode": vehicle.group_kendaraan,
    })


@login_required
def vehicle_search(request):
    """Cari modal: vehicles of every group matching No. Registrasi, Merk/Type,
    No. Chasis or No. Mesin. ``?hasil=1`` returns only the table rows (live search)."""
    q = request.GET.get("q", "").strip()
    vehicles = Vehicle.objects.order_by("nopol")
    if q:
        vehicles = vehicles.filter(
            Q(nopol__icontains=q) | Q(merek__icontains=q) | Q(no_chasis__icontains=q) | Q(no_mesin__icontains=q)
        )
    # Page links reload only the results (?hasil=1), keeping the search text.
    context = {"vehicles": halaman(request, vehicles, hasil=1), "q": q}
    template = "fleet/_vehicle_search_hasil.html" if request.GET.get("hasil") else "fleet/_vehicle_search_modal.html"
    return render(request, template, context)
