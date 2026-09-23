import hashlib

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

    def qr_text(self):
        return "\n".join([
            f"No. Registrasi: {self.nopol}",
            f"Merk/Type: {self.merek}",
            f"No. Chasis: {self.no_chasis or '-'}",
            f"No. Mesin: {self.no_mesin or '-'}",
        ])

    def qr_version(self):
        # Changes whenever the QR content changes, so the image URL changes
        # too and browsers never show a QR cached from before an edit.
        return hashlib.sha256(self.qr_text().encode()).hexdigest()[:10]


class VehiclePhoto(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="fotos")
    image = models.ImageField(upload_to="kendaraan/", verbose_name="Foto Kendaraan")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Foto {self.vehicle.nopol} #{self.pk}"
