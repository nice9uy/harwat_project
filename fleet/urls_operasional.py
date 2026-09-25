from django.urls import path

from . import views

app_name = "operasional"

urlpatterns = [
    path("jadwal/", views.jadwal_list, name="jadwal_list"),
    path("jadwal/tambah/", views.jadwal_form, name="jadwal_create"),
    path("jadwal/<int:pk>/ubah/", views.jadwal_form, name="jadwal_update"),
    path("jadwal/<int:pk>/hapus/", views.jadwal_hapus, name="jadwal_delete"),
    path("servis/", views.servis_list, name="servis_list"),
    path("servis/tambah/", views.servis_form, name="servis_create"),
    path("servis/<int:pk>/ubah/", views.servis_form, name="servis_update"),
    path("servis/<int:pk>/hapus/", views.servis_hapus, name="servis_delete"),
]
