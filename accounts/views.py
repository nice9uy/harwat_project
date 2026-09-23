import secrets
import string

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from fleet.images import compress_photo
from fleet.models import Vehicle
from fleet.services import get_fleet_summary

from . import pemeriksaan
from .forms import BiodataForm, LaporanForm, LoginForm, PemeriksaanGolonganBForm, UserCreateForm
from .models import PemeriksaanGolonganBItem, PerbaikanGolonganB
from .roles import keanggotaan_label


def _get_success_url(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
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
    if request.method == "POST":
        expected = request.session.get("laporan_captcha", "")
        form = LaporanForm(request.POST, request.FILES, expected_captcha=expected)
        pemeriksaan_form = PemeriksaanGolonganBForm(request.POST, request.FILES)
        if form.is_valid() and pemeriksaan_form.is_valid():
            with transaction.atomic():
                pemeriksa = form.save()
                hasil = pemeriksaan_form.save(commit=False)
                hasil.pemeriksa = pemeriksa
                hasil.save()
                for item in pemeriksaan_form.cleaned_items:
                    foto = item.pop("foto")
                    PemeriksaanGolonganBItem.objects.create(
                        pemeriksaan=hasil,
                        foto=compress_photo(foto) if foto else "",
                        **item,
                    )
            del request.session["laporan_captcha"]
            messages.success(request, f"Pemeriksaan {hasil.vehicle.nopol} berhasil disimpan.")
            return redirect("accounts:pemeriksaan")
    else:
        form = LaporanForm()
        pemeriksaan_form = PemeriksaanGolonganBForm()

    captcha_code = _new_captcha_code()
    request.session["laporan_captcha"] = captcha_code
    request.session["laporan_captcha_gagal"] = 0
    return render(request, "accounts/laporan.html", {
        "form": form,
        "pemeriksaan_form": pemeriksaan_form,
        "captcha_code": captcha_code,
        "pembagian_kelas": pemeriksaan.PEMBAGIAN_KELAS,
        "eselon_reparasi": pemeriksaan.ESELON_REPARASI,
        "macam_pemeriksaan": pemeriksaan.MACAM_PEMERIKSAAN,
        "buku_jalan": pemeriksaan.BUKU_JALAN,
        "kondisi": pemeriksaan.KONDISI,
        "alat": pemeriksaan.ALAT_BERNOMOR,
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
    """Golongan B inspections, newest first, with their B/RR/RB counts;
    plus the latest one and its parts rated RR/RB (need repair)."""
    riwayat = list(
        vehicle.pemeriksaan_golongan_b.select_related("pemeriksa")
        .annotate(
            jumlah_b=Count("items", filter=Q(items__kondisi="B")),
            jumlah_rr=Count("items", filter=Q(items__kondisi="RR")),
            jumlah_rb=Count("items", filter=Q(items__kondisi="RB")),
        )
        # Meta.ordering is dropped on GROUP BY queries, so order explicitly.
        .order_by("-dibuat_pada", "-id")
    )
    terakhir = riwayat[0] if riwayat else None
    perlu_perhatian = terakhir.items.exclude(kondisi="B") if terakhir else []
    return riwayat, terakhir, perlu_perhatian


def _perlu_perbaikan(terakhir):
    """RR/RB parts of the latest inspection whose latest repair isn't Baik yet.

    Each item gets ``perbaikan_terakhir`` (its most recent repair or None).
    """
    if terakhir is None:
        return []
    items = terakhir.items.exclude(kondisi="B").prefetch_related(
        Prefetch("perbaikan", queryset=PerbaikanGolonganB.objects.select_related("teknisi"))
    )
    daftar = []
    for item in items:
        repairs = list(item.perbaikan.all())
        item.perbaikan_terakhir = repairs[0] if repairs else None
        if item.perbaikan_terakhir is None or item.perbaikan_terakhir.kondisi != "B":
            daftar.append(item)
    return daftar


@login_required
def history_kendaraan_view(request):
    """Inspection history of the vehicle whose QR code was scanned."""
    vehicle = _vehicle_from_scan(request)
    riwayat, terakhir, _ = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None, [])
    riwayat_perbaikan = []
    if vehicle is not None:
        riwayat_perbaikan = PerbaikanGolonganB.objects.filter(
            item__pemeriksaan__vehicle=vehicle
        ).select_related("item", "teknisi")
    return render(request, "accounts/_history_kendaraan.html", {
        "vehicle": vehicle,
        "riwayat": riwayat,
        "terakhir": terakhir,
        # Parts repaired back to Baik no longer need attention.
        "perlu_perhatian": _perlu_perbaikan(terakhir),
        "riwayat_perbaikan": riwayat_perbaikan,
    })


def _clean_perbaikan(data, files, daftar):
    """Validate the repair fields of the items the technician opened.

    Returns (entries, errors); entries are dicts ready for PerbaikanGolonganB.
    """
    kondisi_valid = {kode for kode, _ in pemeriksaan.KONDISI}
    entries, errors = [], []
    for item in daftar:
        prefix = f"perbaikan_{item.pk}_"
        if not data.get(prefix + "aktif"):
            continue
        label = f"{item.nomor}. {item.nama_alat}"
        kondisi = data.get(prefix + "kondisi", "")
        if kondisi not in kondisi_valid:
            errors.append(f"Kondisi perbaikan {label} belum dipilih.")
        jumlah_raw = data.get(prefix + "jml", "").strip()
        if jumlah_raw and not jumlah_raw.isdigit():
            errors.append(f"Jumlah perbaikan {label} harus angka 0 atau lebih.")
        foto = files.get(prefix + "foto")
        if foto:
            try:
                foto = forms.ImageField().clean(foto)
            except forms.ValidationError:
                errors.append(f"Foto perbaikan {label} bukan gambar yang valid.")
        entries.append({
            "item": item,
            "kondisi": kondisi,
            "jumlah": int(jumlah_raw) if jumlah_raw.isdigit() else None,
            "keterangan": data.get(prefix + "keterangan", "").strip(),
            "foto": foto or None,
        })
    if not entries and not errors:
        errors.append("Pilih minimal satu item lalu klik Perbaikan untuk mengisinya.")
    return entries, errors


@login_required
def perbaikan_view(request):
    errors = []
    if request.method == "POST":
        form = BiodataForm(request.POST, request.FILES)
        vehicle = Vehicle.objects.filter(pk=request.POST.get("vehicle") or None).first()
        if vehicle is None:
            errors.append("Scan QR Code kendaraan terlebih dahulu.")
        else:
            _, terakhir, _ = _riwayat_pemeriksaan(vehicle)
            entries, errors = _clean_perbaikan(request.POST, request.FILES, _perlu_perbaikan(terakhir))
        if form.is_valid() and not errors:
            with transaction.atomic():
                teknisi = form.save()
                for entry in entries:
                    foto = entry.pop("foto")
                    PerbaikanGolonganB.objects.create(
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
        "kondisi": pemeriksaan.KONDISI,
    })


@login_required
def perbaikan_kendaraan_view(request):
    """Parts to repair on the scanned vehicle: RR/RB items of its last inspection."""
    vehicle = _vehicle_from_scan(request)
    _, terakhir, _ = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None, [])
    return render(request, "accounts/_perbaikan_daftar.html", {
        "vehicle": vehicle,
        "terakhir": terakhir,
        "daftar": _perlu_perbaikan(terakhir),
        "kondisi": pemeriksaan.KONDISI,
    })


@login_required
def pengaturan_view(request):
    users = User.objects.prefetch_related("groups").order_by("username")
    for user in users:
        user.keanggotaan = keanggotaan_label(user)
    return render(request, "accounts/pengaturan.html", {"users": users})


@login_required
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST, allow_superuser=request.user.is_superuser)
        if form.is_valid():
            form.save()
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserCreateForm(allow_superuser=request.user.is_superuser)
    is_htmx = request.headers.get("HX-Request") == "true"
    template = "accounts/_user_form_fields.html" if is_htmx else "accounts/user_form.html"
    return render(request, template, {"form": form})
