import secrets
import string

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from fleet.images import compress_photo
from fleet.models import Vehicle
from fleet.services import get_fleet_summary

from . import golongan, pemeriksaan, roles
from .forms import TEXT_INPUT_CLASSES, BiodataForm, SatuanForm, LaporanForm, LoginForm, UserCreateForm, UserEditForm
from .models import Anggota, Satuan
from .roles import keanggotaan_label


def _get_success_url(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    if roles.MENU_PER_KEANGGOTAAN.get(roles.keanggotaan_kode(request.user)):
        return resolve_url(roles.home_view_name(request.user))
    return resolve_url(settings.LOGIN_REDIRECT_URL)


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_get_success_url(request))

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            request.session.set_expiry(1209600 if form.cleaned_data.get("remember_me") else 0)

            success_url = _get_success_url(request)
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")


def _dashboard_context():
    return {
        "fleet_summary": get_fleet_summary(),
        "upcoming_maintenance": [
            {"vehicle": "Truk Angkut B 9021 XY", "service_type": "Ganti oli & filter", "date": "2026-09-28", "status": "Terjadwal"},
            {"vehicle": "Jeep Patroli B 4412 KM", "service_type": "Servis rem", "date": "2026-09-30", "status": "Terjadwal"},
            {"vehicle": "Ambulans B 1187 AD", "service_type": "Servis berkala 20.000 km", "date": "2026-10-03", "status": "Terjadwal"},
        ],
        "overdue_alerts": [
            {"vehicle": "Truk Logistik B 7734 QW", "issue": "Servis berkala lewat 12 hari", "severity": "Tinggi"},
            {"vehicle": "Motor Kurir B 2290 PL", "issue": "Ganti ban lewat jadwal", "severity": "Sedang"},
        ],
        "recent_activity": [
            {"actor": "Budi Santoso", "action": "menyelesaikan servis rutin Truk B 9021 XY", "when": "2 jam lalu"},
            {"actor": "Siti Amalia", "action": "menambahkan catatan servis Jeep B 4412 KM", "when": "5 jam lalu"},
            {"actor": "Rudi Hartono", "action": "melaporkan kendaraan baru Ambulans B 1187 AD", "when": "1 hari lalu"},
        ],
    }


@login_required
def dashboard_view(request):
    return render(request, "accounts/dashboard.html", _dashboard_context())


@login_required
def dashboard_partial(request):
    return render(request, "accounts/_dashboard_content.html", _dashboard_context())


def password_reset_placeholder(request):
    return render(request, "accounts/password_reset_placeholder.html")


CAPTCHA_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def _new_captcha_code():
    return "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(6))


@login_required
def laporan_view(request):
    pemeriksaan_form = None
    if request.method == "POST":
        expected = request.session.get("laporan_captcha", "")
        form = LaporanForm(request.POST, request.FILES, expected_captcha=expected)
        vehicle = Vehicle.objects.filter(pk=request.POST.get("vehicle") or None).first()
        # The vehicle's group picks the checklist; without a (known) vehicle
        # the Golongan B form reports the missing scan.
        golongan_cfg = golongan.for_vehicle(vehicle) or golongan.GOLONGAN[Vehicle.GroupKendaraan.GOLONGAN_B]
        pemeriksaan_form = golongan_cfg.form(request.POST, request.FILES)
        if form.is_valid() and pemeriksaan_form.is_valid():
            with transaction.atomic():
                pemeriksa = form.save()
                hasil = pemeriksaan_form.save(commit=False)
                hasil.pemeriksa = pemeriksa
                hasil.save()
                for item in pemeriksaan_form.cleaned_items:
                    foto = item.pop("foto")
                    golongan_cfg.item_model.objects.create(
                        pemeriksaan=hasil,
                        foto=compress_photo(foto) if foto else "",
                        **item,
                    )
            del request.session["laporan_captcha"]
            messages.success(request, f"Pemeriksaan {hasil.vehicle.nopol} berhasil disimpan.")
            return redirect("accounts:pemeriksaan")
    else:
        form = LaporanForm()

    captcha_code = _new_captcha_code()
    request.session["laporan_captcha"] = captcha_code
    request.session["laporan_captcha_gagal"] = 0
    return render(request, "accounts/laporan.html", {
        "form": form,
        "pemeriksaan_form": pemeriksaan_form,
        "captcha_code": captcha_code,
        # JS array literal for x-data (single quotes: it sits in a "…" attribute).
        "golongan_dengan_form": "[" + ", ".join(f"'{str(kode)}'" for kode in golongan.GOLONGAN) + "]",
    })


@login_required
def pemeriksaan_checklist_view(request, kode):
    """The checklist of one vehicle group, loaded into Form Pemeriksaan after the QR scan.

    Loading only the scanned group's checklist keeps the page small and
    keeps other groups' same-named, required fields out of the form.
    """
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404("Form pemeriksaan untuk golongan ini belum tersedia.")
    return render(request, cfg.template, {
        "kondisi": cfg.kondisi,
        "pakai_jumlah": cfg.pakai_jumlah,
        "pakai_satuan": cfg.pakai_satuan,
        # Golongan B
        "pembagian_kelas": pemeriksaan.PEMBAGIAN_KELAS,
        "eselon_reparasi": pemeriksaan.ESELON_REPARASI,
        "macam_pemeriksaan": pemeriksaan.MACAM_PEMERIKSAAN,
        "buku_jalan": pemeriksaan.BUKU_JALAN,
        "alat_golongan_b": pemeriksaan.ALAT_BERNOMOR,
        # Kendaraan Bermotor
        "buku_harian": pemeriksaan.BUKU_HARIAN,
        "alat_bermotor": pemeriksaan.KOMPONEN_BERMOTOR_BERNOMOR,
        "satuan_list": Satuan.objects.order_by("nama"),
        # Kendaraan Diesel
        "diesel_bab": pemeriksaan.DIESEL_BAB,
        "ya_tidak": pemeriksaan.YA_TIDAK,
        "kondisi_ranmor": pemeriksaan.KONDISI_RANMOR,
    })


CAPTCHA_MAX_GAGAL = 5


@login_required
@require_POST
def pemeriksaan_captcha_view(request):
    """Check the Form Pemeriksaan captcha before the (large) form is posted."""
    expected = request.session.get("laporan_captcha", "")
    if expected and request.POST.get("captcha", "").strip().upper() == expected:
        return JsonResponse({"ok": True})
    gagal = request.session.get("laporan_captcha_gagal", 0) + 1
    request.session["laporan_captcha_gagal"] = gagal
    if gagal >= CAPTCHA_MAX_GAGAL:
        # Rotate the code so it can't be brute-forced through this endpoint.
        code = _new_captcha_code()
        request.session["laporan_captcha"] = code
        request.session["laporan_captcha_gagal"] = 0
        return JsonResponse({"ok": False, "error": "Terlalu banyak percobaan. Kode baru sudah dibuat.", "code": code})
    return JsonResponse({"ok": False, "error": "Kode keamanan tidak sesuai."})


@login_required
def form_tambah_view(request):
    return render(request, "accounts/form_tambah.html", {"form": LaporanForm()})


@login_required
def history_view(request):
    return render(request, "accounts/history.html")


def _vehicle_from_scan(request):
    return (
        Vehicle.objects.prefetch_related("fotos")
        .filter(nopol=request.GET.get("nopol", "").strip())
        .first()
    )


def _riwayat_pemeriksaan(vehicle):
    """Inspections of the vehicle's group, newest first, each with
    ``kondisi_counts`` [(kode, label, count)]; plus the latest one."""
    cfg = golongan.for_vehicle(vehicle)
    if cfg is None:
        return [], None
    riwayat = list(
        getattr(vehicle, cfg.relasi).select_related("pemeriksa")
        .annotate(**{
            f"jumlah_{kode}": Count("items", filter=Q(items__kondisi=kode)) for kode, _ in cfg.kondisi
        })
        # Meta.ordering is dropped on GROUP BY queries, so order explicitly.
        .order_by("-dibuat_pada", "-id")
    )
    for hasil in riwayat:
        hasil.kondisi_counts = [(kode, label, getattr(hasil, f"jumlah_{kode}")) for kode, label in cfg.kondisi]
    return riwayat, (riwayat[0] if riwayat else None)


def _perlu_perbaikan(vehicle, terakhir):
    """Parts of the latest inspection not rated Baik whose latest repair isn't Baik yet.

    Each item gets ``perbaikan_terakhir`` (its most recent repair or None).
    """
    if terakhir is None:
        return []
    cfg = golongan.for_vehicle(vehicle)
    items = terakhir.items.exclude(kondisi__in=cfg.baik).prefetch_related(
        Prefetch("perbaikan", queryset=cfg.perbaikan_model.objects.select_related("teknisi"))
    )
    daftar = []
    for item in items:
        repairs = list(item.perbaikan.all())
        item.perbaikan_terakhir = repairs[0] if repairs else None
        if item.perbaikan_terakhir is None or item.perbaikan_terakhir.kondisi not in cfg.baik:
            daftar.append(item)
    return daftar


@login_required
def history_kendaraan_view(request):
    """Inspection and repair history of the vehicle whose QR code was scanned."""
    vehicle = _vehicle_from_scan(request)
    riwayat, terakhir = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None)
    riwayat_perbaikan = []
    cfg = golongan.for_vehicle(vehicle)
    if cfg is not None:
        riwayat_perbaikan = cfg.perbaikan_model.objects.filter(
            item__pemeriksaan__vehicle=vehicle
        ).select_related("item", "teknisi")
    return render(request, "accounts/_history_kendaraan.html", {
        "vehicle": vehicle,
        "riwayat": riwayat,
        "terakhir": terakhir,
        # Parts repaired back to Baik no longer need attention.
        "perlu_perhatian": _perlu_perbaikan(vehicle, terakhir),
        "riwayat_perbaikan": riwayat_perbaikan,
        "pakai_jumlah": cfg.pakai_jumlah if cfg else False,
        "pakai_satuan": cfg.pakai_satuan if cfg else False,
    })


def _clean_perbaikan(data, files, daftar, kondisi, pakai_jumlah):
    """Validate the repair fields of the items the technician opened.

    Returns (entries, errors); entries are dicts ready for the group's repair model.
    """
    kondisi_valid = {kode for kode, _ in kondisi}
    entries, errors = [], []
    for item in daftar:
        prefix = f"perbaikan_{item.pk}_"
        if not data.get(prefix + "aktif"):
            continue
        label = f"{item.nomor}. {item.nama_alat}"
        kode = data.get(prefix + "kondisi", "")
        if kode not in kondisi_valid:
            errors.append(f"Kondisi perbaikan {label} belum dipilih.")
        jumlah_raw = data.get(prefix + "jml", "").strip() if pakai_jumlah else ""
        if jumlah_raw and not jumlah_raw.isdigit():
            errors.append(f"Jumlah perbaikan {label} harus angka 0 atau lebih.")
        foto = files.get(prefix + "foto")
        if foto:
            try:
                foto = forms.ImageField().clean(foto)
            except forms.ValidationError:
                errors.append(f"Foto perbaikan {label} bukan gambar yang valid.")
        entry = {
            "item": item,
            "kondisi": kode,
            "keterangan": data.get(prefix + "keterangan", "").strip(),
            "foto": foto or None,
        }
        if pakai_jumlah:
            entry["jumlah"] = int(jumlah_raw) if jumlah_raw.isdigit() else None
        entries.append(entry)
    if not entries and not errors:
        errors.append("Pilih minimal satu item lalu klik Perbaikan untuk mengisinya.")
    return entries, errors


@login_required
def perbaikan_view(request):
    errors = []
    if request.method == "POST":
        form = BiodataForm(request.POST, request.FILES)
        vehicle = Vehicle.objects.filter(pk=request.POST.get("vehicle") or None).first()
        cfg = golongan.for_vehicle(vehicle)
        if cfg is None:
            errors.append("Scan QR Code kendaraan terlebih dahulu.")
        else:
            _, terakhir = _riwayat_pemeriksaan(vehicle)
            entries, errors = _clean_perbaikan(
                request.POST, request.FILES, _perlu_perbaikan(vehicle, terakhir), cfg.kondisi, cfg.pakai_jumlah,
            )
        if form.is_valid() and not errors:
            with transaction.atomic():
                teknisi = form.save()
                for entry in entries:
                    foto = entry.pop("foto")
                    cfg.perbaikan_model.objects.create(
                        teknisi=teknisi, foto=compress_photo(foto) if foto else "", **entry,
                    )
            messages.success(request, f"Perbaikan {vehicle.nopol} berhasil disimpan ({len(entries)} item).")
            return redirect(f"{reverse('accounts:perbaikan')}?{urlencode({'nopol': vehicle.nopol})}")
    else:
        form = BiodataForm()
    return render(request, "accounts/perbaikan.html", {
        "form": form,
        "perbaikan_errors": errors,
        "nopol": request.GET.get("nopol", ""),
    })


@login_required
def perbaikan_kendaraan_view(request):
    """Parts to repair on the scanned vehicle: non-Baik items of its last inspection."""
    vehicle = _vehicle_from_scan(request)
    _, terakhir = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None)
    cfg = golongan.for_vehicle(vehicle)
    return render(request, "accounts/_perbaikan_daftar.html", {
        "vehicle": vehicle,
        "terakhir": terakhir,
        "daftar": _perlu_perbaikan(vehicle, terakhir),
        "kondisi": cfg.kondisi if cfg else [],
        "pakai_jumlah": cfg.pakai_jumlah if cfg else False,
        "pakai_satuan": cfg.pakai_satuan if cfg else False,
    })


@login_required
def pengaturan_view(request):
    """Users outside the team tree first, then each Ketua Tim followed by its members."""
    semua = {u.pk: u for u in User.objects.prefetch_related("groups").order_by("username")}
    users, dalam_pohon, tree = [], set(), []
    nodes = list(Anggota.get_tree().select_related("user"))
    # Ketua Tim (roots) and their members, each sorted by username.
    for ketua in sorted((n for n in nodes if n.depth == 1), key=lambda n: n.user.username):
        anggota = sorted(
            (n for n in nodes if n.depth == 2 and n.path.startswith(ketua.path)), key=lambda n: n.user.username,
        )
        for node in [ketua, *anggota]:
            akun = semua[node.user_id]
            akun.kedalaman = node.depth - 1
            akun.ketua_tim = ketua.user.username if node.depth > 1 else ""
            akun.anggota_pk = node.pk if node.depth == 1 else None
            akun.ketua_pk = ketua.pk  # which branch a member row collapses with
            akun.jumlah_anggota = len(anggota) if node.depth == 1 else 0
            tree.append(akun)
            dalam_pohon.add(akun.pk)
    for akun in semua.values():
        if akun.pk not in dalam_pohon:
            akun.kedalaman, akun.ketua_tim = 0, ""
            users.append(akun)
    users += tree
    for akun in users:
        akun.keanggotaan = keanggotaan_label(akun)
    return render(request, "accounts/pengaturan.html", {
        "users": users,
        "satuan_list": Satuan.objects.all(),
        "tab": "satuan" if request.GET.get("tab") == "satuan" else "user",
    })


@login_required
def user_create(request):
    # ?ketua=<Anggota pk>: add a member directly under that Ketua Tim.
    ketua = Anggota.get_root_nodes().select_related("user").filter(pk=request.GET.get("ketua") or None).first()
    kwargs = {"allow_superuser": request.user.is_superuser, "ketua": ketua}
    if request.method == "POST":
        form = UserCreateForm(request.POST, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserCreateForm(**kwargs)
    is_htmx = request.headers.get("HX-Request") == "true"
    template = "accounts/_user_form_fields.html" if is_htmx else "accounts/user_form.html"
    return render(request, template, {"form": form})


@login_required
def user_delete(request, pk):
    """GET: confirmation for the Pengaturan modal. POST: delete the user.

    Superusers and the logged-in user's own account can't be deleted here.
    """
    akun = get_object_or_404(User, pk=pk)
    if akun.is_superuser or akun.pk == request.user.pk:
        messages.error(request, f"User {akun.username} tidak bisa dihapus.")
        return redirect("accounts:pengaturan")
    node = getattr(akun, "anggota", None)
    if node is not None and node.get_children_count():
        messages.error(request, f"Ketua Tim {akun.username} masih punya anggota. Hapus atau pindahkan anggotanya dulu.")
        return redirect("accounts:pengaturan")
    if request.method == "POST":
        with transaction.atomic():
            # Delete the tree node through treebeard so the parent's child count stays right.
            if node is not None:
                node.delete()
            akun.delete()
        messages.success(request, f"User {akun.username} berhasil dihapus.")
        return redirect("accounts:pengaturan")
    return render(request, "accounts/_user_delete_confirm.html", {"akun": akun, "keanggotaan": keanggotaan_label(akun)})


def _boleh_ubah(request, akun):
    """Nobody changes their own role here, and only a superuser touches a superuser."""
    return akun.pk != request.user.pk and (request.user.is_superuser or not akun.is_superuser)


@login_required
def user_edit(request, pk):
    """Change a user's keanggotaan / Ketua Tim from the Pengaturan modal."""
    akun = get_object_or_404(User, pk=pk)
    if not _boleh_ubah(request, akun):
        messages.error(request, f"Keanggotaan {akun.username} tidak bisa diubah.")
        return redirect("accounts:pengaturan")
    kwargs = {"user": akun, "allow_superuser": request.user.is_superuser}
    if request.method == "POST":
        form = UserEditForm(request.POST, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f"Keanggotaan {akun.username} berhasil diubah.")
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserEditForm(**kwargs)
    return render(request, "accounts/_user_edit_form.html", {"form": form, "akun": akun})


@login_required
def ganti_password_view(request):
    """Change the logged-in user's own password (open to every role)."""
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # stay logged in
            messages.success(request, "Password berhasil diganti.")
            return redirect("accounts:ganti_password")
    else:
        form = PasswordChangeForm(request.user)
    for field in form.fields.values():
        field.widget.attrs["class"] = TEXT_INPUT_CLASSES
    return render(request, "accounts/ganti_password.html", {"form": form})


def _ke_tab_satuan(request):
    url = f"{reverse('accounts:pengaturan')}?tab=satuan"
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


@login_required
def satuan_form_view(request, pk=None):
    """Tambah (pk=None) or Edit a Satuan in the Pengaturan modal."""
    satuan = get_object_or_404(Satuan, pk=pk) if pk else None
    if request.method == "POST":
        form = SatuanForm(request.POST, instance=satuan)
        if form.is_valid():
            simpan = form.save()
            messages.success(request, f"Satuan {simpan.nama} berhasil disimpan.")
            return _ke_tab_satuan(request)
    else:
        form = SatuanForm(instance=satuan)
    return render(request, "accounts/_satuan_form.html", {"form": form, "satuan": satuan})


@login_required
def satuan_delete(request, pk):
    """GET: confirmation for the modal. POST: delete the Satuan."""
    satuan = get_object_or_404(Satuan, pk=pk)
    if request.method == "POST":
        if satuan.biodata.exists() or satuan.pemeriksaan_golongan_b.exists():
            messages.error(request, f"Satuan {satuan.nama} masih dipakai di biodata atau pemeriksaan, jadi tidak bisa dihapus.")
            return _ke_tab_satuan(request)
        satuan.delete()
        messages.success(request, f"Satuan {satuan.nama} berhasil dihapus.")
        return _ke_tab_satuan(request)
    return render(request, "accounts/_satuan_delete_confirm.html", {"satuan": satuan})
