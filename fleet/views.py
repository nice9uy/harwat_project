from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Vehicle


@login_required
def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, "fleet/vehicle_list.html", {"vehicles": vehicles})
