"""Form Rusak/Tidak Layak Pakai: a Tim member declares a scanned vehicle
beyond use, with the reason and up to four photos. The vehicle becomes Rusak
Berat (golongan.status_kendaraan) and shows on the dashboard's Rusak/Tidak
Bisa Diperbaiki tab."""
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from fleet.images import compress_photo
from fleet.models import Vehicle

from . import golongan
from .forms import clean_foto
from .models import KendaraanRusak, Laporan


def _kendaraan(nilai):
    try:
        return Vehicle.objects.filter(uuid=uuid.UUID(nilai or "")).first()
    except ValueError:
        return None


@login_required
def rusak_view(request):
    """The page (scan or type a No. Registrasi), and POST: save the declaration."""
    laporan_user = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    errors = []
    if request.method == "POST":
        vehicle = _kendaraan(request.POST.get("vehicle"))
        alasan = request.POST.get("alasan", "").strip()
        if not laporan_user:
            errors.append("Isi biodata di Info Profil terlebih dahulu.")
        if vehicle is None:
            errors.append("Scan QR Code kendaraan terlebih dahulu.")
        if not alasan:
            errors.append("Isi alasan / keterangan kerusakan.")
        fotos = clean_foto(request.FILES, "rusak_foto", "kerusakan", errors)
        if not errors:
            with transaction.atomic():
                KendaraanRusak.objects.create(
                    vehicle=vehicle, pelapor=laporan_user, alasan=alasan,
                    **KendaraanRusak.kolom_foto([compress_photo(f) for f in fotos]),
                )
                golongan.perbarui_status(vehicle)
            messages.success(request, f"Kendaraan {vehicle.nopol} dinyatakan Rusak/Tidak Layak Pakai.")
            return redirect(f"{reverse('accounts:rusak')}?{urlencode({'nopol': vehicle.nopol})}")
    return render(request, "accounts/rusak.html", {
        "laporan_user": laporan_user, "rusak_errors": errors, "nopol": request.GET.get("nopol", ""),
    })


@login_required
def rusak_kendaraan_view(request):
    """The form for the scanned vehicle, with what was declared of it before."""
    vehicle = Vehicle.objects.filter(nopol=request.GET.get("nopol", "").strip()).first()
    return render(request, "accounts/_rusak_form.html", {
        "vehicle": vehicle,
        "riwayat": list(vehicle.rusak.select_related("pelapor")) if vehicle else [],
    })
