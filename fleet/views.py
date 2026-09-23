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


@login_required
def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, "fleet/vehicle_list.html", {"vehicles": vehicles})


@login_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            if _is_htmx(request):
                return _htmx_redirect(reverse("fleet:vehicle_list"))
            return redirect("fleet:vehicle_list")
    else:
        form = VehicleForm()
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {"form": form, "is_edit": False})


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
@require_POST
def vehicle_delete(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
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
