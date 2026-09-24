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
    path("pemeriksaan/cek-captcha/", views.pemeriksaan_captcha_view, name="pemeriksaan_captcha"),
    # Old address, kept so bookmarks keep working.
    path("laporan/", RedirectView.as_view(pattern_name="accounts:pemeriksaan", permanent=True)),
    path("form-tambah/", views.form_tambah_view, name="form_tambah"),
    path("history/", views.history_view, name="history"),
    path("history/kendaraan/", views.history_kendaraan_view, name="history_kendaraan"),
    path("perbaikan/", views.perbaikan_view, name="perbaikan"),
    path("perbaikan/kendaraan/", views.perbaikan_kendaraan_view, name="perbaikan_kendaraan"),
    path("pengaturan/", views.pengaturan_view, name="pengaturan"),
    path("pengaturan/user/tambah/", views.user_create, name="user_create"),
    path("pengaturan/user/<int:pk>/hapus/", views.user_delete, name="user_delete"),
    path("pengaturan/user/<int:pk>/ubah/", views.user_edit, name="user_edit"),
]
