"""The Hapus action of Laporan Pemeriksaan, Perbaikan and Penambahan: each of
their rows is a vehicle, and deleting a row deletes what that report shows of
it. Superusers only; confirmed with a code to retype."""
import secrets
import string

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import FileField
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from fleet.models import Vehicle

from . import golongan

# jenis -> (the report's url name, its title, what a row's deletion removes)
JENIS = {
    "pemeriksaan": ("accounts:laporan_pemeriksaan", "Laporan Pemeriksaan"),
    "perbaikan": ("accounts:laporan_perbaikan", "Laporan Perbaikan"),
    "penambahan": ("accounts:laporan_penambahan", "Laporan Penambahan Kendaraan/Barang"),
    "rusak": ("accounts:laporan_rusak", "Laporan Rusak/Tidak Layak Pakai"),
}


def boleh_hapus(user):
    return user.is_superuser


def _berkas(objek):
    """The files (photos) of model instances, to remove once their rows are gone."""
    hasil = []
    for o in objek:
        for f in o._meta.fields:
            if isinstance(f, FileField) and getattr(o, f.name):
                hasil.append(getattr(o, f.name))
    return hasil


def _catatan(vehicle, jenis):
    """(rows to delete, everything whose files go with them) for a vehicle's
    inspections or repairs, over every group's models."""
    hapus, ikut = [], []
    for cfg in golongan.GOLONGAN.values():
        perbaikan = list(cfg.perbaikan_model.objects.filter(item__pemeriksaan__vehicle=vehicle))
        if jenis == "perbaikan":
            hapus += perbaikan
            ikut += perbaikan
        else:
            pemeriksaan = list(cfg.pemeriksaan_model.objects.filter(vehicle=vehicle))
            hapus += pemeriksaan
            ikut += pemeriksaan + perbaikan + list(cfg.item_model.objects.filter(pemeriksaan__vehicle=vehicle))
    return hapus, ikut


def _halangan_penambahan(vehicle):
    """Why the vehicle itself can't be deleted yet, or ''."""
    if any(getattr(vehicle, cfg.relasi).exists() for cfg in golongan.GOLONGAN.values()):
        return "masih punya laporan pemeriksaan. Hapus dulu di Laporan Pemeriksaan."
    if vehicle.servis.exists():
        return "masih punya catatan servis. Hapus dulu di menu Servis."
    return ""


@login_required
def laporan_hapus(request, jenis, uid):
    if jenis not in JENIS:
        raise Http404
    if not boleh_hapus(request.user):
        return HttpResponse(status=403)
    url_laporan, judul = JENIS[jenis]
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    konteks = {"vehicle": vehicle, "jenis": jenis, "judul": judul}

    if jenis == "penambahan":
        hapus, ikut = [vehicle], [*vehicle.fotos.all(), *vehicle.rusak.all()]
        konteks["halangan"] = _halangan_penambahan(vehicle)
    elif jenis == "rusak":
        # The declarations only; the vehicle's status follows its inspections again.
        hapus = ikut = list(vehicle.rusak.all())
    else:
        hapus, ikut = _catatan(vehicle, jenis)
    konteks["jumlah"] = len(hapus)
    if konteks.get("halangan"):
        return render(request, "accounts/_laporan_hapus.html", konteks)

    session_key = f"hapus_laporan_{jenis}_{vehicle.pk}"
    if request.method == "POST":
        kode_benar = request.session.get(session_key)
        if not kode_benar or request.POST.get("captcha", "").strip() != kode_benar:
            messages.error(request, "Kode verifikasi salah.")
            return redirect(url_laporan)
        del request.session[session_key]
        berkas = _berkas(ikut)
        with transaction.atomic():
            for o in hapus:
                o.delete()
            if jenis != "penambahan":
                golongan.perbarui_status(vehicle)
        # Rows cascade, but the photo files would otherwise stay in storage.
        for b in berkas:
            b.delete(save=False)
        apa = {
            "pemeriksaan": "Laporan pemeriksaan", "perbaikan": "Laporan perbaikan", "penambahan": "Kendaraan",
            "rusak": "Pernyataan rusak/tidak layak pakai",
        }[jenis]
        messages.success(request, f"{apa} {vehicle.nopol} berhasil dihapus.")
        return redirect(url_laporan)

    kode = "".join(secrets.choice(string.digits) for _ in range(6))
    request.session[session_key] = kode
    konteks.update({"captcha_kode": kode, "url": reverse("accounts:laporan_hapus", args=[jenis, vehicle.uuid])})
    return render(request, "accounts/_laporan_hapus.html", konteks)
