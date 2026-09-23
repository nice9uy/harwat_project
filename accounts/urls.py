from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "accounts"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="accounts:login", permanent=False)),
    path("login/", views.login_view, name="login"),
    path("lupa-password/", views.password_reset_placeholder, name="password_reset_placeholder"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("pengaturan/", views.pengaturan_view, name="pengaturan"),
]
