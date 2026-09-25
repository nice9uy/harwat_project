from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from django.utils.text import slugify

from accounts.paging import halaman

from .forms import JadwalForm, ServisForm, VehicleForm
from .models import Jadwal, Servis, Vehicle
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
    from accounts.forms import BiodataForm  # accounts imports fleet models

    next_url = _next_url(request)
    # ?penambah=1 (Form Tambah): the page's biodata comes along and is saved
    # as the vehicle's penambah.
    pakai_biodata = bool(request.GET.get("penambah"))
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        form.instance.group_kendaraan = _group(request)
        form.instance.ditambahkan_oleh = request.user
        biodata = BiodataForm(request.POST, request.FILES, prefix="penambah") if pakai_biodata else None
        if biodata is not None and not biodata.is_valid():
            form.add_error(None, "Biodata pemeriksa belum lengkap. Tutup form ini dan periksa kembali biodatanya.")
        if form.is_valid():
            with transaction.atomic():
                if biodata is not None:
                    biodata.instance.akun = request.user
                    form.instance.penambah = biodata.save()
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
        "pakai_biodata": pakai_biodata,
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


# --- Jadwal and Servis: a table per menu, add / edit / delete in a modal ---

CATATAN = {
    "jadwal": {"model": Jadwal, "form": JadwalForm, "judul": "Jadwal"},
    "servis": {"model": Servis, "form": ServisForm, "judul": "Servis"},
}


def _ke_daftar(request, jenis):
    url = reverse(f"operasional:{jenis}_list")
    if _is_htmx(request):
        return _htmx_redirect(url)
    return redirect(url)


def _catatan_form(request, jenis, pk=None):
    cfg = CATATAN[jenis]
    obj = get_object_or_404(cfg["model"], pk=pk) if pk else None
    if request.method == "POST":
        form = cfg["form"](request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"{cfg['judul']} berhasil disimpan.")
            return _ke_daftar(request, jenis)
    else:
        form = cfg["form"](instance=obj, initial={"vehicle": request.GET.get("kendaraan")} if not obj else None)
    return render(request, "fleet/_catatan_form.html", {
        "form": form,
        "obj": obj,
        "judul": cfg["judul"],
        "post_url": request.get_full_path(),
    })


def _catatan_hapus(request, jenis, pk):
    cfg = CATATAN[jenis]
    obj = get_object_or_404(cfg["model"], pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, f"{cfg['judul']} berhasil dihapus.")
        return _ke_daftar(request, jenis)
    return render(request, "fleet/_catatan_hapus.html", {"obj": obj, "judul": cfg["judul"], "post_url": request.path})


@login_required
def jadwal_list(request):
    return render(request, "fleet/jadwal_list.html", {
        "jadwal_list": halaman(request, Jadwal.objects.select_related("vehicle")),
    })


@login_required
def jadwal_form(request, pk=None):
    return _catatan_form(request, "jadwal", pk)


@login_required
def jadwal_hapus(request, pk):
    return _catatan_hapus(request, "jadwal", pk)


@login_required
def servis_list(request):
    servis_list = Servis.objects.select_related("vehicle")
    return render(request, "fleet/servis_list.html", {
        "servis_list": halaman(request, servis_list),
        "total_biaya": servis_list.aggregate(total=Sum("biaya"))["total"] or 0,
    })


@login_required
def servis_form(request, pk=None):
    return _catatan_form(request, "servis", pk)


@login_required
def servis_hapus(request, pk):
    return _catatan_hapus(request, "servis", pk)
