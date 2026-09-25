from django.contrib import admin

from treebeard.admin import TreeAdmin
from treebeard.forms import movenodeform_factory

from .models import (
    Anggota,
    Laporan,
    PemeriksaanBermotor,
    PemeriksaanBermotorItem,
    PemeriksaanDiesel,
    PemeriksaanDieselItem,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanBermotor,
    PerbaikanDiesel,
    PerbaikanGolonganB,
    RevokedToken,
    Satuan,
)


@admin.register(Laporan)
class LaporanAdmin(admin.ModelAdmin):
    list_display = ["nama", "nip", "pangkat", "jabatan", "satuan", "dibuat_pada"]
    list_filter = ["satuan"]
    search_fields = ["nama", "nip", "satuan__nama"]
    date_hierarchy = "dibuat_pada"
    list_select_related = ["satuan"]
    raw_id_fields = ["akun"]


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
    list_select_related = ["vehicle", "pemeriksa", "kesatuan"]
    search_fields = ["vehicle__nopol", "pemeriksa__nama", "pemeriksa__nip", "kesatuan__nama"]
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


class PemeriksaanBermotorItemInline(admin.TabularInline):
    model = PemeriksaanBermotorItem
    extra = 0


@admin.register(PemeriksaanBermotor)
class PemeriksaanBermotorAdmin(admin.ModelAdmin):
    list_display = [
        "vehicle", "pemeriksa", "bbm", "buku_harian", "macam_pemeriksaan", "tempat_pemeriksaan", "ukuran_ban", "dibuat_pada",
    ]
    list_filter = ["macam_pemeriksaan", "buku_harian"]
    list_select_related = ["vehicle", "pemeriksa"]
    search_fields = ["vehicle__nopol", "pemeriksa__nama", "pemeriksa__nip", "tempat_pemeriksaan"]
    date_hierarchy = "dibuat_pada"
    inlines = [PemeriksaanBermotorItemInline]


@admin.register(PemeriksaanBermotorItem)
class PemeriksaanBermotorItemAdmin(admin.ModelAdmin):
    list_display = ["pemeriksaan", "nomor", "nama_alat", "kondisi", "keterangan"]
    list_filter = ["kondisi", "nama_alat"]
    list_select_related = ["pemeriksaan__vehicle"]
    search_fields = ["pemeriksaan__vehicle__nopol", "nama_alat", "keterangan"]


@admin.register(PerbaikanBermotor)
class PerbaikanBermotorAdmin(admin.ModelAdmin):
    list_display = ["item", "kendaraan", "kondisi", "teknisi", "dibuat_pada"]
    list_filter = ["kondisi"]
    list_select_related = ["item__pemeriksaan__vehicle", "teknisi"]
    search_fields = ["item__pemeriksaan__vehicle__nopol", "item__nama_alat", "teknisi__nama", "keterangan"]
    date_hierarchy = "dibuat_pada"

    @admin.display(description="Kendaraan", ordering="item__pemeriksaan__vehicle__nopol")
    def kendaraan(self, obj):
        return obj.item.pemeriksaan.vehicle


@admin.register(Anggota)
class AnggotaAdmin(TreeAdmin):
    form = movenodeform_factory(Anggota)
    list_display = ["user"]
    list_select_related = ["user"]


class PemeriksaanDieselItemInline(admin.TabularInline):
    model = PemeriksaanDieselItem
    extra = 0


@admin.register(PemeriksaanDiesel)
class PemeriksaanDieselAdmin(admin.ModelAdmin):
    list_display = ["vehicle", "pemeriksa", "km_mil", "jam_mesin", "buku_pemeliharaan", "kondisi_ranmor", "dibuat_pada"]
    list_filter = ["macam_pemeriksaan", "kondisi_ranmor", "buku_pemeliharaan"]
    list_select_related = ["vehicle", "pemeriksa"]
    search_fields = ["vehicle__nopol", "pemeriksa__nama", "pemeriksa__nip"]
    date_hierarchy = "dibuat_pada"
    inlines = [PemeriksaanDieselItemInline]


@admin.register(PemeriksaanDieselItem)
class PemeriksaanDieselItemAdmin(admin.ModelAdmin):
    list_display = ["pemeriksaan", "nomor", "nama_alat", "satuan", "jumlah_riil", "jumlah_nyata", "kondisi", "keterangan"]
    list_filter = ["kondisi"]
    list_select_related = ["pemeriksaan__vehicle"]
    search_fields = ["pemeriksaan__vehicle__nopol", "nama_alat", "keterangan"]


@admin.register(PerbaikanDiesel)
class PerbaikanDieselAdmin(admin.ModelAdmin):
    list_display = ["item", "kendaraan", "kondisi", "teknisi", "dibuat_pada"]
    list_filter = ["kondisi"]
    list_select_related = ["item__pemeriksaan__vehicle", "teknisi"]
    search_fields = ["item__pemeriksaan__vehicle__nopol", "item__nama_alat", "teknisi__nama", "keterangan"]
    date_hierarchy = "dibuat_pada"

    @admin.display(description="Kendaraan", ordering="item__pemeriksaan__vehicle__nopol")
    def kendaraan(self, obj):
        return obj.item.pemeriksaan.vehicle


@admin.register(Satuan)
class SatuanAdmin(admin.ModelAdmin):
    list_display = ["nama", "keterangan", "dibuat_pada"]
    search_fields = ["nama", "keterangan"]
