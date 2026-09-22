from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import VehicleForm
from .models import Vehicle


@login_required
def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, "fleet/vehicle_list.html", {"vehicles": vehicles})


@login_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("fleet:vehicle_list")
    else:
        form = VehicleForm()
    return render(request, "fleet/vehicle_form.html", {"form": form, "is_edit": False})
