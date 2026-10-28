"""The Hapus action of Laporan Pemeriksaan, Perbaikan and Penambahan: each of
their rows is a vehicle, and deleting a row deletes what that report shows of
it. Superuser, Admin and Ketua Tim (roles.boleh_ubah_laporan); confirmed
with a code to retype."""
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

from . import golongan, roles

# jenis -> (the report's url name, its title, what a row's deletion removes)
JENIS = {
    "pemeriksaan": ("accounts:laporan_pemeriksaan", "Laporan Pemeriksaan"),
    "perbaikan": ("accounts:laporan_perbaikan", "Laporan Perbaikan"),
    "penambahan": ("accounts:laporan_penambahan", "Laporan Penambahan Kendaraan/Barang"),
    "rusak": ("accounts:laporan_rusak", "Laporan Rusak/Tidak Layak Pakai"),
}


def boleh_hapus(user):
    return roles.boleh_ubah_laporan(user)


def _berkas(objek):
    """The files (photos) of model instances, to remove once their rows are gone."""
    hasil = []
    for o in objek:
        for f in o._meta.fields:
            if isinstance(f, FileField) and getattr(o, f.name):
                hasil.append(getattr(o, f.name))
    return hasil


def _milik(qs, field, users):
    """``qs`` narrowed to the work of ``users`` (the viewer's team(s)), None: all."""
    return qs if users is None else qs.filter(**{f"{field}__in": users})


def _catatan(vehicle, jenis, users=None):
    """(rows to delete, everything whose files go with them) for a vehicle's
    inspections or repairs, over every group's models; ``users``: only those
    of the viewer's team(s), as the report shows them (None: all)."""
    hapus, ikut = [], []
    for cfg in golongan.GOLONGAN.values():
        if jenis == "perbaikan":
            perbaikan = list(_milik(
                cfg.perbaikan_model.objects.filter(item__pemeriksaan__vehicle=vehicle), "teknisi__akun", users,
            ))
            hapus += perbaikan
            ikut += perbaikan
        else:
            pemeriksaan = list(_milik(cfg.pemeriksaan_model.objects.filter(vehicle=vehicle), "pemeriksa__akun", users))
            hapus += pemeriksaan
            # Their items, and the repairs of those items, go with them.
            ikut += pemeriksaan + list(cfg.perbaikan_model.objects.filter(item__pemeriksaan__in=pemeriksaan))
            ikut += list(cfg.item_model.objects.filter(pemeriksaan__in=pemeriksaan))
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
    from .dashboard import cakupan_laporan

    users = cakupan_laporan(request.user)
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    # A Ketua Tim deletes what their report shows: their team's work only.
    if jenis == "penambahan" and users is not None and vehicle.ditambahkan_oleh_id not in users:
        raise Http404
    konteks = {"vehicle": vehicle, "jenis": jenis, "judul": judul}

    if jenis == "penambahan":
        hapus, ikut = [vehicle], [*vehicle.fotos.all(), *vehicle.rusak.all()]
        konteks["halangan"] = _halangan_penambahan(vehicle)
    elif jenis == "rusak":
        # The declarations only; the vehicle's status follows its inspections again.
        hapus = ikut = list(_milik(vehicle.rusak.all(), "pelapor__akun", users))
    else:
        hapus, ikut = _catatan(vehicle, jenis, users)
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
