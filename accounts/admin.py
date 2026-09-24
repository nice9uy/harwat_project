from django.contrib import admin

from .models import (
    Laporan,
    PemeriksaanMotor,
    PemeriksaanMotorItem,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanMotor,
    PerbaikanGolonganB,
    RevokedToken,
)


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


class PemeriksaanGolonganBItemInline(admin.TabularInline):
    model = PemeriksaanGolonganBItem
    extra = 0


@admin.register(PemeriksaanGolonganB)
class PemeriksaanGolonganBAdmin(admin.ModelAdmin):
    list_display = [
        "vehicle", "pemeriksa", "pembagian_kelas", "eselon_reparasi",
        "macam_pemeriksaan", "buku_jalan", "kesatuan", "dibuat_pada",
    ]
    list_filter = ["macam_pemeriksaan", "pembagian_kelas", "eselon_reparasi", "buku_jalan"]
    list_select_related = ["vehicle", "pemeriksa"]
    search_fields = ["vehicle__nopol", "pemeriksa__nama", "pemeriksa__nip", "kesatuan"]
    date_hierarchy = "dibuat_pada"
    inlines = [PemeriksaanGolonganBItemInline]


@admin.register(PemeriksaanGolonganBItem)
class PemeriksaanGolonganBItemAdmin(admin.ModelAdmin):
    list_display = ["pemeriksaan", "nomor", "nama_alat", "jumlah", "kondisi", "keterangan"]
    list_filter = ["kondisi", "nama_alat"]
    list_select_related = ["pemeriksaan__vehicle"]
    search_fields = ["pemeriksaan__vehicle__nopol", "nama_alat", "keterangan"]


@admin.register(PerbaikanGolonganB)
class PerbaikanGolonganBAdmin(admin.ModelAdmin):
    list_display = ["item", "kendaraan", "kondisi", "jumlah", "teknisi", "dibuat_pada"]
    list_filter = ["kondisi"]
    list_select_related = ["item__pemeriksaan__vehicle", "teknisi"]
    search_fields = ["item__pemeriksaan__vehicle__nopol", "item__nama_alat", "teknisi__nama", "keterangan"]
    date_hierarchy = "dibuat_pada"

    @admin.display(description="Kendaraan", ordering="item__pemeriksaan__vehicle__nopol")
    def kendaraan(self, obj):
        return obj.item.pemeriksaan.vehicle


class PemeriksaanMotorItemInline(admin.TabularInline):
    model = PemeriksaanMotorItem
    extra = 0


@admin.register(PemeriksaanMotor)
class PemeriksaanMotorAdmin(admin.ModelAdmin):
    list_display = [
        "vehicle", "pemeriksa", "bbm", "buku_harian", "macam_pemeriksaan", "tempat_pemeriksaan", "ukuran_ban", "dibuat_pada",
    ]
    list_filter = ["macam_pemeriksaan", "buku_harian"]
    list_select_related = ["vehicle", "pemeriksa"]
    search_fields = ["vehicle__nopol", "pemeriksa__nama", "pemeriksa__nip", "tempat_pemeriksaan"]
    date_hierarchy = "dibuat_pada"
    inlines = [PemeriksaanMotorItemInline]


@admin.register(PemeriksaanMotorItem)
class PemeriksaanMotorItemAdmin(admin.ModelAdmin):
    list_display = ["pemeriksaan", "nomor", "nama_alat", "kondisi", "keterangan"]
    list_filter = ["kondisi", "nama_alat"]
    list_select_related = ["pemeriksaan__vehicle"]
    search_fields = ["pemeriksaan__vehicle__nopol", "nama_alat", "keterangan"]


@admin.register(PerbaikanMotor)
class PerbaikanMotorAdmin(admin.ModelAdmin):
    list_display = ["item", "kendaraan", "kondisi", "teknisi", "dibuat_pada"]
    list_filter = ["kondisi"]
    list_select_related = ["item__pemeriksaan__vehicle", "teknisi"]
    search_fields = ["item__pemeriksaan__vehicle__nopol", "item__nama_alat", "teknisi__nama", "keterangan"]
    date_hierarchy = "dibuat_pada"

    @admin.display(description="Kendaraan", ordering="item__pemeriksaan__vehicle__nopol")
    def kendaraan(self, obj):
        return obj.item.pemeriksaan.vehicle
