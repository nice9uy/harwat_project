from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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


@login_required
def vehicle_list(request):
    group = _group(request)
    vehicles = Vehicle.objects.filter(group_kendaraan=group).prefetch_related("fotos")
    return render(request, "fleet/vehicle_list.html", {
        "vehicles": vehicles,
        "group": group,
        "group_label": Vehicle.GroupKendaraan(group).label,
    })


@login_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        form.instance.group_kendaraan = _group(request)
        if form.is_valid():
            form.save()
            if _is_htmx(request):
                return _htmx_redirect(reverse("fleet:vehicle_list"))
            return redirect("fleet:vehicle_list")
    else:
        form = VehicleForm()
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {"form": form, "is_edit": False, "group": _group(request)})


@login_required
def vehicle_update(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            if _is_htmx(request):
                return _htmx_redirect(reverse("fleet:vehicle_list"))
            return redirect("fleet:vehicle_list")
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
    # Rows cascade, but the image files would otherwise stay on disk.
    for foto in vehicle.fotos.all():
        foto.image.delete(save=False)
    vehicle.delete()
    return redirect("fleet:vehicle_list")


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
