from django.urls import path

from . import views

app_name = "fleet"

urlpatterns = [
    path("", views.vehicle_list, name="vehicle_list"),
]
