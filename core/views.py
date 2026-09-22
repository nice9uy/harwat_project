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
    return render(request, "core/login.html", {"form": LoginForm(request)})


def password_reset_placeholder(request):
    return render(request, "core/password_reset_placeholder.html")
