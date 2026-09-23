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
    path("dashboard/partial/", views.dashboard_partial, name="dashboard_partial"),
    path("pemeriksaan/", views.laporan_view, name="pemeriksaan"),
    # Old address, kept so bookmarks keep working.
    path("laporan/", RedirectView.as_view(pattern_name="accounts:pemeriksaan", permanent=True)),
    path("form-tambah/", views.form_tambah_view, name="form_tambah"),
    path("pengaturan/", views.pengaturan_view, name="pengaturan"),
    path("pengaturan/user/tambah/", views.user_create, name="user_create"),
]
