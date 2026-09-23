from django.db import models


class Vehicle(models.Model):
    class Jenis(models.TextChoices):
        TRUK = "truk", "Truk"
        JEEP = "jeep", "Jeep"
        MOTOR = "motor", "Motor"
        AMBULANS = "ambulans", "Ambulans"
        MOBIL = "mobil", "Mobil"
        LAINNYA = "lainnya", "Lainnya"

    class Status(models.TextChoices):
        SIAP_PAKAI = "siap_pakai", "Siap Pakai"
        DALAM_PERBAIKAN = "dalam_perbaikan", "Dalam Perbaikan"
        PERLU_SERVIS = "perlu_servis", "Perlu Servis"

    nopol = models.CharField(max_length=20, unique=True, verbose_name="No. Registrasi")
    jenis = models.CharField(max_length=20, choices=Jenis.choices, blank=True)
    merek = models.CharField(max_length=100, verbose_name="Merk/Type")
    tahun = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Tahun")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SIAP_PAKAI)
    odometer_km = models.PositiveIntegerField(default=0, verbose_name="Km / Mil")
    penanggung_jawab = models.CharField(max_length=150, blank=True, verbose_name="Penanggung Jawab")
    no_chasis = models.CharField(max_length=50, blank=True, verbose_name="No. Chasis")
    no_mesin = models.CharField(max_length=50, blank=True, verbose_name="No. Mesin")

    class Meta:
        ordering = ["nopol"]

    def __str__(self):
        return self.nopol
