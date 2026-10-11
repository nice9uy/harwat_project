from django.urls import path

from . import views

app_name = "fleet"

urlpatterns = [
    path("", views.vehicle_list, name="vehicle_list"),
    path("tambah/", views.vehicle_create, name="vehicle_create"),
    path("cari/", views.vehicle_lookup, name="vehicle_lookup"),
    path("pencarian/", views.vehicle_search, name="vehicle_search"),
    path("<uuid:uid>/edit/", views.vehicle_update, name="vehicle_update"),
    path("<uuid:uid>/hapus/", views.vehicle_delete, name="vehicle_delete"),
    path("<uuid:uid>/hapus/konfirmasi/", views.vehicle_delete_confirm, name="vehicle_delete_confirm"),
    path("<uuid:uid>/qr.png", views.vehicle_qr, name="vehicle_qr"),
    path("<uuid:uid>/foto/", views.vehicle_photos, name="vehicle_photos"),
    path("<uuid:uid>/qr/", views.vehicle_qr_modal, name="vehicle_qr_modal"),
]
