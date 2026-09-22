from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import LoginForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            request.session.set_expiry(1209600 if form.cleaned_data.get("remember_me") else 0)

            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = "/dashboard/"
                return response
            return redirect("core:dashboard")
    else:
        form = LoginForm(request)

    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    from django.contrib.auth import logout as auth_logout

    auth_logout(request)
    return redirect("core:login")


@login_required
def dashboard_view(request):
    context = {
        "fleet_summary": {
            "total": 42,
            "ready": 31,
            "in_repair": 7,
            "due_soon": 4,
        },
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
    return render(request, "core/dashboard.html", context)


def password_reset_placeholder(request):
    return render(request, "core/password_reset_placeholder.html")
