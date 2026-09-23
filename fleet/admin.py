from django.contrib import admin

from .models import Vehicle, VehiclePhoto


class VehiclePhotoInline(admin.TabularInline):
    model = VehiclePhoto
    extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["nopol", "group_kendaraan", "merek", "no_chasis", "no_mesin", "status"]
    list_filter = ["group_kendaraan", "status", "jenis"]
    search_fields = ["nopol", "merek", "no_chasis", "no_mesin"]
    inlines = [VehiclePhotoInline]


@admin.register(VehiclePhoto)
class VehiclePhotoAdmin(admin.ModelAdmin):
    list_display = ["id", "vehicle", "image"]
    list_select_related = ["vehicle"]
    search_fields = ["vehicle__nopol"]
