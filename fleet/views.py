from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from django.utils.text import slugify

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


def _list_url(group):
    """Armada list on the given group's tab (the default tab needs no query)."""
    url = reverse("fleet:vehicle_list")
    return url if group == Vehicle.GroupKendaraan.GOLONGAN_B else f"{url}?{urlencode({'group': group})}"


@login_required
def vehicle_list(request):
    group = _group(request)
    vehicles = Vehicle.objects.filter(group_kendaraan=group).prefetch_related("fotos")
    return render(request, "fleet/vehicle_list.html", {
        "vehicles": vehicles,
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
    next_url = _next_url(request)
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        form.instance.group_kendaraan = _group(request)
        if form.is_valid():
            vehicle = form.save()
            if next_url:
                messages.success(request, f"Kendaraan {vehicle.nopol} berhasil ditambahkan.")
            target = next_url or _list_url(vehicle.group_kendaraan)
            if _is_htmx(request):
                return _htmx_redirect(target)
            return redirect(target)
    else:
        form = VehicleForm()
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {
        "form": form, "is_edit": False, "group": _group(request), "next_url": next_url or "",
    })


@login_required
def vehicle_update(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            if _is_htmx(request):
                return _htmx_redirect(_list_url(vehicle.group_kendaraan))
            return redirect(_list_url(vehicle.group_kendaraan))
    else:
        form = VehicleForm(instance=vehicle)
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {"form": form, "is_edit": True, "vehicle": vehicle})


@login_required
def vehicle_delete_confirm(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    return render(request, "fleet/_vehicle_delete_confirm.html", {"vehicle": vehicle})


@login_required
@require_POST
def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if vehicle.pemeriksaan_golongan_b.exists() or vehicle.pemeriksaan_bermotor.exists():
        messages.error(request, f"Kendaraan {vehicle.nopol} tidak bisa dihapus karena sudah punya data pemeriksaan.")
        return redirect(_list_url(vehicle.group_kendaraan))
    # Rows cascade, but the image files would otherwise stay on disk.
    for foto in vehicle.fotos.all():
        foto.image.delete(save=False)
    vehicle.delete()
    return redirect(_list_url(vehicle.group_kendaraan))


@login_required
def vehicle_qr(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    response = HttpResponse(qr_png_with_logo(vehicle.qr_text()), content_type="image/png")
    response["Cache-Control"] = "private, no-cache"
    if request.GET.get("unduh"):
        response["Content-Disposition"] = f'attachment; filename="qr-{slugify(vehicle.nopol)}.png"'
    return response


@login_required
def vehicle_photos(request, pk):
    vehicle = get_object_or_404(Vehicle.objects.prefetch_related("fotos"), pk=pk)
    return render(request, "fleet/_vehicle_photos_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_qr_modal(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    return render(request, "fleet/_vehicle_qr_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_lookup(request):
    """Vehicle details for a scanned QR code, looked up by No. Registrasi."""
    vehicle = Vehicle.objects.filter(nopol=request.GET.get("nopol", "").strip()).first()
    if vehicle is None:
        return JsonResponse({"error": "Kendaraan tidak ditemukan."}, status=404)
    return JsonResponse({
        "id": vehicle.pk,
        "nopol": vehicle.nopol,
        "merek": vehicle.merek,
        "no_chasis": vehicle.no_chasis,
        "no_mesin": vehicle.no_mesin,
        "group_kendaraan": vehicle.get_group_kendaraan_display(),
        "group_kode": vehicle.group_kendaraan,
    })


PENCARIAN_MAKS = 50


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
    total = vehicles.count()
    context = {"vehicles": vehicles[:PENCARIAN_MAKS], "total": total, "q": q, "maks": PENCARIAN_MAKS}
    template = "fleet/_vehicle_search_rows.html" if request.GET.get("hasil") else "fleet/_vehicle_search_modal.html"
    return render(request, template, context)
