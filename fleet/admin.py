from django.contrib import admin

from .models import Jadwal, NonKendaraan, Servis, Vehicle, VehiclePhoto


class VehiclePhotoInline(admin.TabularInline):
    model = VehiclePhoto
    extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["nopol", "group_kendaraan", "merek", "no_chasis", "no_mesin", "kepemilikan", "matra", "status"]
    list_filter = ["group_kendaraan", "matra", "kepemilikan", "status", "jenis"]
    search_fields = ["nopol", "merek", "no_chasis", "no_mesin"]
    raw_id_fields = ["ditambahkan_oleh", "penambah"]
    inlines = [VehiclePhotoInline]


@admin.register(VehiclePhoto)
class VehiclePhotoAdmin(admin.ModelAdmin):
    list_display = ["id", "vehicle", "image"]
    list_select_related = ["vehicle"]
    search_fields = ["vehicle__nopol"]


@admin.register(Jadwal)
class JadwalAdmin(admin.ModelAdmin):
    list_display = ["tanggal", "vehicle", "kegiatan", "status", "keterangan"]
    list_filter = ["kegiatan", "status"]
    list_select_related = ["vehicle"]
    search_fields = ["vehicle__nopol", "keterangan"]
    date_hierarchy = "tanggal"


@admin.register(Servis)
class ServisAdmin(admin.ModelAdmin):
    list_display = ["tanggal", "vehicle", "jenis_servis", "bengkel", "biaya"]
    list_select_related = ["vehicle"]
    search_fields = ["vehicle__nopol", "jenis_servis", "bengkel", "keterangan"]
    date_hierarchy = "tanggal"


@admin.register(NonKendaraan)
class NonKendaraanAdmin(admin.ModelAdmin):
    list_display = ["kode_barang", "group", "nama_barang", "merek", "no_seri", "jumlah", "satuan", "kondisi"]
    list_filter = ["group", "kondisi"]
    search_fields = ["kode_barang", "nama_barang", "merek", "no_seri"]
    raw_id_fields = ["ditambahkan_oleh"]
