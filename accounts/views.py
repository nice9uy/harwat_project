import secrets
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from fleet.services import get_fleet_summary

from .forms import LaporanForm, LoginForm, UserCreateForm


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
        if form.is_valid():
            form.save()
            del request.session["laporan_captcha"]
            messages.success(request, "Laporan berhasil dikirim.")
            return redirect("accounts:laporan")
    else:
        form = LaporanForm()

    captcha_code = _new_captcha_code()
    request.session["laporan_captcha"] = captcha_code
    return render(request, "accounts/laporan.html", {"form": form, "captcha_code": captcha_code})


@login_required
def form_tambah_view(request):
    return render(request, "accounts/form_tambah.html")


@login_required
def pengaturan_view(request):
    users = User.objects.all().order_by("username")
    return render(request, "accounts/pengaturan.html", {"users": users})


@login_required
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserCreateForm()
    is_htmx = request.headers.get("HX-Request") == "true"
    template = "accounts/_user_form_fields.html" if is_htmx else "accounts/user_form.html"
    return render(request, template, {"form": form})
