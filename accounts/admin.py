from django.contrib import admin

from .models import Laporan, RevokedToken


@admin.register(Laporan)
class LaporanAdmin(admin.ModelAdmin):
    list_display = ["nama", "nip", "pangkat", "jabatan", "satuan", "dibuat_pada"]
    list_filter = ["satuan"]
    search_fields = ["nama", "nip", "satuan"]
    date_hierarchy = "dibuat_pada"


@admin.register(RevokedToken)
class RevokedTokenAdmin(admin.ModelAdmin):
    list_display = ["jti", "revoked_at", "expires_at"]
    search_fields = ["jti"]
