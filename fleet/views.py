from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.utils import timezone
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


def _matra(request):
    """The matra a vehicle is added for: the one a superadmin picked on Form
    Tambah (?matra=), anyone else's own; "" when there is none."""
    from accounts import roles  # accounts imports fleet models

    if not request.user.is_superuser:
        return getattr(getattr(request.user, "publik", None), "matra", "")
    matra = request.GET.get("matra", "")
    return matra if matra in dict(roles.MATRA) else ""


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
    from accounts import roles, status
    from accounts.models import Laporan, PekerjaanAktif  # accounts imports fleet models

    # Form Group may keep a Tim Penambahan Data member off some vehicle groups.
    if _group(request) not in roles.form_tambah_boleh(request.user):
        if _is_htmx(request):
            # Say so in the modal: a bare 403 leaves HTMX showing nothing, as
            # if Simpan did nothing (the access may be taken away while the
            # form is open).
            return render(request, "fleet/_vehicle_form_terlarang.html", {
                "label": dict(roles.FORM_TAMBAH)[_group(request)],
            })
        return HttpResponse(status=403)
    next_url = _next_url(request)
    pakai_biodata = bool(request.GET.get("penambah"))
    laporan_penambah = None
    if pakai_biodata:
        laporan_penambah = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        form.instance.group_kendaraan = _group(request)
        form.instance.ditambahkan_oleh = request.user
        form.instance.matra = _matra(request)
        if pakai_biodata and laporan_penambah is None:
            form.add_error(None, "Isi biodata di Info Profil terlebih dahulu.")
        if form.is_valid():
            with transaction.atomic():
                if pakai_biodata and laporan_penambah:
                    form.instance.penambah = laporan_penambah
                vehicle = form.save()
            status.selesai(request.user, PekerjaanAktif.Jenis.PENAMBAHAN)
            if next_url:
                messages.success(request, f"Kendaraan {vehicle.nopol} berhasil ditambahkan.")
            target = next_url or _list_url(vehicle.group_kendaraan)
            if _is_htmx(request):
                return _htmx_redirect(target)
            return redirect(target)
    else:
        form = VehicleForm()
        if pakai_biodata:
            # Shown on the member's Status menu until the vehicle is saved or cancelled.
            status.mulai(
                request.user, PekerjaanAktif.Jenis.PENAMBAHAN,
                keterangan=dict(roles.FORM_TAMBAH)[_group(request)],
            )
    template = "fleet/_vehicle_form_fields.html" if _is_htmx(request) else "fleet/vehicle_form.html"
    return render(request, template, {
        "form": form, "is_edit": False, "group": _group(request), "next_url": next_url or "",
        "pakai_biodata": pakai_biodata, "matra": _matra(request),
        "matra_label": dict(roles.MATRA).get(_matra(request), ""),
    })


@login_required
def vehicle_update(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
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
def vehicle_delete_confirm(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    return render(request, "fleet/_vehicle_delete_confirm.html", {"vehicle": vehicle})


@login_required
@require_POST
def vehicle_delete(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
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
def vehicle_qr(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    response = HttpResponse(qr_png_with_logo(vehicle.qr_text(), label=vehicle.nopol), content_type="image/png")
    response["Cache-Control"] = "private, no-cache"
    if request.GET.get("unduh"):
        response["Content-Disposition"] = f'attachment; filename="qr-{slugify(vehicle.nopol)}.png"'
    return response


@login_required
def vehicle_photos(request, uid):
    vehicle = get_object_or_404(Vehicle.objects.prefetch_related("fotos"), uuid=uid)
    return render(request, "fleet/_vehicle_photos_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_qr_modal(request, uid):
    vehicle = get_object_or_404(Vehicle, uuid=uid)
    return render(request, "fleet/_vehicle_qr_modal.html", {"vehicle": vehicle})


@login_required
def vehicle_lookup(request):
    """Vehicle details for a scanned QR code, looked up by No. Registrasi."""
    vehicle = Vehicle.objects.filter(nopol=request.GET.get("nopol", "").strip()).first()
    if vehicle is None:
        return JsonResponse({"error": "Kendaraan tidak ditemukan."}, status=404)
    return JsonResponse({
        "uuid": str(vehicle.uuid),
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


def _catatan_form(request, jenis, uid=None):
    cfg = CATATAN[jenis]
    obj = get_object_or_404(cfg["model"], uuid=uid) if uid else None
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


def _catatan_hapus(request, jenis, uid):
    cfg = CATATAN[jenis]
    obj = get_object_or_404(cfg["model"], uuid=uid)
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
def jadwal_form(request, uid=None):
    return _catatan_form(request, "jadwal", uid)


@login_required
def jadwal_hapus(request, uid):
    return _catatan_hapus(request, "jadwal", uid)


def _servis_dan_perbaikan():
    """The Servis table's rows, newest first: the services recorded here and
    the repairs saved in Form Perbaikan (one row per repaired part). A repair
    that left the part Rusak (RB) is not a service: it shows under Rusak/Tidak
    Bisa Diperbaiki instead."""
    from accounts.golongan import GOLONGAN  # accounts depends on fleet, not the other way round

    baris = [
        {
            "tanggal": s.tanggal, "waktu": s.dibuat_pada, "vehicle": s.vehicle, "jenis_servis": s.jenis_servis,
            "bengkel": s.bengkel, "keterangan": s.keterangan, "servis": s, "form_no": "", "kondisi": "",
        }
        for s in Servis.objects.select_related("vehicle__penambah__satuan")
    ]
    for cfg in GOLONGAN.values():
        for p in (
            cfg.perbaikan_model.objects.exclude(kondisi="RB")
            .select_related("teknisi", "item__pemeriksaan__vehicle__penambah__satuan")
        ):
            waktu = timezone.localtime(p.dibuat_pada)
            baris.append({
                "tanggal": waktu.date(), "waktu": p.dibuat_pada, "vehicle": p.item.pemeriksaan.vehicle,
                "form_no": p.item.nomor, "jenis_servis": f"Perbaikan {p.item.nama_alat}", "kondisi": p.kondisi,
                "teknisi": p.teknisi.nama,
                "keterangan": " · ".join(filter(None, [f"Kondisi: {p.get_kondisi_display()}", p.keterangan])),
                "servis": None,
            })
    for b in baris:
        # The vehicle's unit: that of the member who added it.
        penambah = b["vehicle"].penambah
        b["satuan"] = penambah.satuan.nama if penambah and penambah.satuan else ""
    baris.sort(key=lambda b: (b["tanggal"], b["waktu"]), reverse=True)
    return baris


# The Kondisi filter of the Servis table: what a repair left the part as
# (accounts.pemeriksaan.KONDISI_PERBAIKAN; a repair left Rusak isn't listed).
KONDISI_SERVIS = [("B", "Baik"), ("RR", "Perlu Servis")]


def _filter_servis(request):
    """The Servis table's filter: ?dari= and ?sampai= (dates), ?nopol= (part
    of a No. Registrasi) and ?kondisi= (a KONDISI_SERVIS code)."""
    from accounts.laporan import _tanggal  # accounts depends on fleet, not the other way round

    kondisi = request.GET.get("kondisi", "")
    return {
        "dari": _tanggal(request.GET.get("dari")), "sampai": _tanggal(request.GET.get("sampai")),
        "nopol": request.GET.get("nopol", "").strip(),
        "kondisi": kondisi if kondisi in dict(KONDISI_SERVIS) else "",
    }


def _saring_servis(baris, f):
    nopol = f["nopol"].lower()
    return [
        b for b in baris
        if not (f["dari"] and b["tanggal"] < f["dari"])
        and not (f["sampai"] and b["tanggal"] > f["sampai"])
        and (not nopol or nopol in b["vehicle"].nopol.lower())
        # A service recorded here has no condition: a Kondisi filter leaves the repairs only.
        and (not f["kondisi"] or b["kondisi"] == f["kondisi"])
    ]


@login_required
def servis_list(request):
    f = _filter_servis(request)
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "fleet/servis_list.html", {
        "servis_list": halaman(request, _saring_servis(_servis_dan_perbaikan(), f)),
        "f": f, "kondisi_pilihan": KONDISI_SERVIS, "query": query.urlencode(),
    })


@login_required
def servis_export(request):
    """The Servis table as filtered (every row, not just the page shown) as an .xlsx sheet."""
    from accounts.laporan import _excel  # accounts depends on fleet, not the other way round

    rows = [
        [
            b["tanggal"].strftime("%d-%m-%Y"), b["vehicle"].nopol, b["vehicle"].merek, b["satuan"], b["form_no"], b["jenis_servis"],
            b["bengkel"] if b["servis"] else f"Teknisi: {b['teknisi']}", b["keterangan"],
            "Servis" if b["servis"] else "Form Perbaikan",
        ]
        for b in _saring_servis(_servis_dan_perbaikan(), _filter_servis(request))
    ]
    return _excel(
        "Servis", ["Tanggal", "No. Registrasi", "Merk/Type", "Satuan", "Form No", "Jenis Servis", "Bengkel / Tempat", "Keterangan", "Sumber"],
        rows, {"dari": None, "sampai": None, "golongan": "", "satuan": None},
        f"servis-{timezone.localtime():%Y%m%d}.xlsx",
    )


@login_required
def servis_form(request, uid=None):
    return _catatan_form(request, "servis", uid)


@login_required
def servis_hapus(request, uid):
    return _catatan_hapus(request, "servis", uid)
