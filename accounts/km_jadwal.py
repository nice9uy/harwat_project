"""Pengaturan > KM: the parts marked * on the inspection form and every how
many km each is due a check."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.db.models import Max
from django.utils import timezone

from fleet.models import Servis, Vehicle

from . import golongan, pemeriksaan
from .forms import TEXT_INPUT_CLASSES
from .models import KmJadwal


def bertanda():
    """The parts marked * on the inspection forms: [(komponen, form, label)],
    the forms' own KM fields first, then Motor's parts in checklist order."""
    hasil = [
        (pemeriksaan.KM_GOLONGAN_B, "Golongan B", pemeriksaan.KM_GOLONGAN_B),
        # Keyed with their form: these share a name with another form's field.
        (f"{pemeriksaan.KM_GOLONGAN_B} (Motor)", "Motor", pemeriksaan.KM_GOLONGAN_B),
        (f"{pemeriksaan.KM_DIESEL} (Kendaraan Diesel)", "Kendaraan Diesel", pemeriksaan.KM_DIESEL),
        (f"{pemeriksaan.KM_DIESEL} (Jeep Diesel)", "Jeep Diesel", pemeriksaan.KM_DIESEL),
        (f"{pemeriksaan.KM_DIESEL} (RANTIS)", "RANTIS", pemeriksaan.KM_DIESEL),
        (f"{pemeriksaan.KM_DIESEL} (RANSUS)", "RANSUS", pemeriksaan.KM_DIESEL),
    ]
    hasil += [
        (nama, "Motor", f"{nomor}. {nama}")
        for nomor, nama in pemeriksaan.KOMPONEN_BERMOTOR_BERNOMOR if nama in pemeriksaan.KOMPONEN_BERMOTOR_KM
    ]
    return hasil


def daftar():
    """One row per marked part. Migrations make the rows; one missing (a part
    marked later) is made here."""
    tanda = bertanda()
    ada = {k.komponen: k for k in KmJadwal.objects.filter(komponen__in=[t[0] for t in tanda])}
    hasil = []
    for komponen, form, label in tanda:
        k = ada.get(komponen) or KmJadwal.objects.create(komponen=komponen)
        k.form, k.label = form, label
        hasil.append(k)
    return hasil


class KmJadwalForm(forms.ModelForm):
    class Meta:
        model = KmJadwal
        fields = ["interval_km", "interval_bulan"]
        widgets = {
            "interval_km": forms.NumberInput(attrs={
                "class": TEXT_INPUT_CLASSES, "min": 1, "step": 500, "inputmode": "numeric", "placeholder": "5000",
            }),
            "interval_bulan": forms.NumberInput(attrs={
                "class": TEXT_INPUT_CLASSES, "min": 1, "max": 120, "inputmode": "numeric", "placeholder": "6",
            }),
        }


@login_required
def km_jadwal_edit(request, uid):
    """Set a marked part's km interval and Waktu Servis in the Pengaturan modal."""
    tanda = {komponen: (form, label) for komponen, form, label in bertanda()}
    obj = get_object_or_404(KmJadwal, uuid=uid, komponen__in=tanda)
    obj.form, obj.label = tanda[obj.komponen]
    if request.method == "POST":
        form = KmJadwalForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Interval {obj.label} ({obj.form}) berhasil disimpan.")
            url = f"{reverse('accounts:pengaturan')}?tab=km"
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = url
                return response
            return redirect(url)
    else:
        form = KmJadwalForm(instance=obj)
    return render(request, "accounts/_km_jadwal_form.html", {"form": form, "obj": obj})


# Per vehicle group: its KmJadwal row (the form's own KM field, marked *) and
# the inspection column holding the odometer reading.
KM_GOLONGAN = {
    Vehicle.GroupKendaraan.GOLONGAN_B: (pemeriksaan.KM_GOLONGAN_B, "km_kendaraan"),
    Vehicle.GroupKendaraan.KENDARAAN_BERMOTOR: (f"{pemeriksaan.KM_GOLONGAN_B} (Motor)", "km_kendaraan"),
    Vehicle.GroupKendaraan.KENDARAAN_DIESEL: (f"{pemeriksaan.KM_DIESEL} (Kendaraan Diesel)", "km_mil"),
    Vehicle.GroupKendaraan.JEEP_DIESEL: (f"{pemeriksaan.KM_DIESEL} (Jeep Diesel)", "km_mil"),
    Vehicle.GroupKendaraan.RANTIS: (f"{pemeriksaan.KM_DIESEL} (RANTIS)", "km_mil"),
    Vehicle.GroupKendaraan.RANSUS: (f"{pemeriksaan.KM_DIESEL} (RANSUS)", "km_mil"),
}


def _bulan_antara(awal, akhir):
    """Whole months from ``awal`` to ``akhir`` (dates)."""
    bulan = (akhir.year - awal.year) * 12 + akhir.month - awal.month
    return bulan - 1 if akhir.day < awal.day else bulan


def perlu_servis(vehicles):
    """{vehicle pk: reason} for the vehicles due a service, by the intervals
    of Pengaturan > KM for their group (a group with neither set is never due):

    * Waktu Servis: that many months since the last service (a Servis record
      or a repair), or since the vehicle was added when it never had one;
    * Interval KM: the latest odometer reading (from the inspections) is that
      many km past the reading at the last service (0 when never serviced, or
      no reading by then).
    """
    vehicles = list(vehicles)
    aturan = {k.komponen: k for k in KmJadwal.objects.all()}
    ids = [v.pk for v in vehicles]
    servis = dict(Servis.objects.filter(vehicle__in=ids).values_list("vehicle").annotate(t=Max("tanggal")))
    bacaan = {}  # vehicle pk -> [(date, km)], oldest first
    for kode, cfg in golongan.GOLONGAN.items():
        kolom = KM_GOLONGAN[kode][1]
        for vid, waktu in (
            cfg.perbaikan_model.objects.filter(item__pemeriksaan__vehicle__in=ids)
            .values_list("item__pemeriksaan__vehicle").annotate(t=Max("dibuat_pada"))
        ):
            tanggal = timezone.localtime(waktu).date()
            servis[vid] = max(tanggal, servis.get(vid, tanggal))
        for vid, waktu, km in (
            cfg.pemeriksaan_model.objects.filter(vehicle__in=ids).exclude(**{kolom: None})
            .order_by("dibuat_pada", "id").values_list("vehicle_id", "dibuat_pada", kolom)
        ):
            bacaan.setdefault(vid, []).append((timezone.localtime(waktu).date(), km))
    hari_ini = timezone.localdate()
    hasil = {}
    for v in vehicles:
        a = aturan.get(KM_GOLONGAN.get(v.group_kendaraan, ("",))[0])
        if a is None or not (a.interval_km or a.interval_bulan):
            continue
        terakhir = servis.get(v.pk)
        alasan = []
        if a.interval_bulan:
            acuan = terakhir or (timezone.localtime(v.dibuat_pada).date() if v.dibuat_pada else None)
            if acuan and _bulan_antara(acuan, hari_ini) >= a.interval_bulan:
                alasan.append(f"{_bulan_antara(acuan, hari_ini)} bulan sejak {'servis terakhir' if terakhir else 'ditambahkan'}")
        if a.interval_km and bacaan.get(v.pk):
            km_kini = bacaan[v.pk][-1][1]
            km_servis = max((km for tanggal, km in bacaan[v.pk] if terakhir and tanggal <= terakhir), default=0)
            if km_kini - km_servis >= a.interval_km:
                alasan.append(f"{km_kini - km_servis} km sejak {'servis terakhir' if km_servis else 'awal'}")
        if alasan:
            hasil[v.pk] = " · ".join(alasan)
    return hasil
