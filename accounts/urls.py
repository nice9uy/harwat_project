from django.urls import path
from django.views.generic import RedirectView

from . import laporan, laporan_pdf, laporan_tim, views

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
    path("pemeriksaan/checklist/<str:kode>/", views.pemeriksaan_checklist_view, name="pemeriksaan_checklist"),
    # Old address, kept so bookmarks keep working.
    path("laporan/", RedirectView.as_view(pattern_name="accounts:pemeriksaan", permanent=True)),
    path("form-tambah/", views.form_tambah_view, name="form_tambah"),
    path("history/", views.history_view, name="history"),
    path("history/kendaraan/", views.history_kendaraan_view, name="history_kendaraan"),
    path("history/kendaraan/modal/", views.history_kendaraan_modal_view, name="history_kendaraan_modal"),
    path("perbaikan/", views.perbaikan_view, name="perbaikan"),
    path("perbaikan/kendaraan/", views.perbaikan_kendaraan_view, name="perbaikan_kendaraan"),
    path("pengaturan/", views.pengaturan_view, name="pengaturan"),
    path("pengaturan/user/tambah/", views.user_create, name="user_create"),
    path("pengaturan/user/<int:pk>/hapus/", views.user_delete, name="user_delete"),
    path("pengaturan/user/<int:pk>/ubah/", views.user_edit, name="user_edit"),
    path("ganti-password/", views.ganti_password_view, name="ganti_password"),
    path("laporan-pemeriksaan/", laporan.laporan_pemeriksaan, name="laporan_pemeriksaan"),
    path(
        "laporan-pemeriksaan/kendaraan/<int:pk>/", laporan.laporan_pemeriksaan_detail,
        name="laporan_pemeriksaan_detail",
    ),
    path(
        "laporan-pemeriksaan/<str:kode>/<int:pk>/pdf/", laporan_pdf.laporan_pemeriksaan_pdf,
        name="laporan_pemeriksaan_pdf",
    ),
    path("laporan-perbaikan/", laporan.laporan_perbaikan, name="laporan_perbaikan"),
    path("laporan-perbaikan/kendaraan/<int:pk>/", laporan.laporan_perbaikan_detail, name="laporan_perbaikan_detail"),
    path(
        "laporan-perbaikan/<str:kode>/<int:pk>/pdf/", laporan_pdf.laporan_perbaikan_pdf,
        name="laporan_perbaikan_pdf",
    ),
    path("laporan-penambahan/", laporan.laporan_penambahan, name="laporan_penambahan"),
    path(
        "laporan-penambahan/kendaraan/<int:pk>/", laporan.laporan_penambahan_detail,
        name="laporan_penambahan_detail",
    ),
    path("laporan-penambahan/<int:pk>/pdf/", laporan_pdf.laporan_penambahan_pdf, name="laporan_penambahan_pdf"),
    path("laporan-tim/", laporan_tim.laporan_tim, name="laporan_tim"),
    path("laporan-tim/<int:pk>/", laporan_tim.laporan_tim_detail, name="laporan_tim_detail"),
    path("laporan-tim/<int:pk>/pdf/", laporan_pdf.laporan_tim_pdf, name="laporan_tim_pdf"),
    path("pengaturan/satuan/tambah/", views.satuan_form_view, name="satuan_create"),
    path("pengaturan/satuan/<int:pk>/ubah/", views.satuan_form_view, name="satuan_update"),
    path("pengaturan/satuan/<int:pk>/hapus/", views.satuan_delete, name="satuan_delete"),
]
