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

    class GroupKendaraan(models.TextChoices):
        GOLONGAN_B = "B", "Golongan B"
        KENDARAAN_BERMOTOR = "bermotor", "Kendaraan Bermotor"
        KENDARAAN_DIESEL = "diesel", "Kendaraan Diesel"

    class Status(models.TextChoices):
        SIAP_PAKAI = "siap_pakai", "Siap Pakai"
        DALAM_PERBAIKAN = "dalam_perbaikan", "Dalam Perbaikan"
        PERLU_SERVIS = "perlu_servis", "Perlu Servis"

    group_kendaraan = models.CharField(
        max_length=10,
        choices=GroupKendaraan.choices,
        default=GroupKendaraan.GOLONGAN_B,
        db_index=True,
        verbose_name="Group Kendaraan",
    )
    nopol = models.CharField(max_length=20, unique=True, verbose_name="No. Registrasi")
    jenis = models.CharField(max_length=20, choices=Jenis.choices, blank=True)
    merek = models.CharField(max_length=100, verbose_name="Merk/Type")
    tahun = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Tahun")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SIAP_PAKAI)
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



class Jadwal(models.Model):
    """A planned activity for a vehicle (inspection, service, repair, ...)."""

    class Kegiatan(models.TextChoices):
        PEMERIKSAAN = "pemeriksaan", "Pemeriksaan"
        SERVIS = "servis", "Servis"
        PERBAIKAN = "perbaikan", "Perbaikan"
        LAINNYA = "lainnya", "Lainnya"

    class Status(models.TextChoices):
        TERJADWAL = "terjadwal", "Terjadwal"
        SELESAI = "selesai", "Selesai"
        DIBATALKAN = "dibatalkan", "Dibatalkan"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="jadwal", verbose_name="Kendaraan")
    tanggal = models.DateField()
    kegiatan = models.CharField(max_length=20, choices=Kegiatan.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TERJADWAL)
    keterangan = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jadwal"
        verbose_name_plural = "Jadwal"
        ordering = ["tanggal", "id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.get_kegiatan_display()} {self.tanggal:%d-%m-%Y}"

    @property
    def terlambat(self):
        from django.utils import timezone

        return self.status == self.Status.TERJADWAL and self.tanggal < timezone.localdate()


class Servis(models.Model):
    """A service carried out on a vehicle (oil change, tune-up, ...)."""

    # PROTECT: service history must not vanish with the vehicle.
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="servis", verbose_name="Kendaraan")
    tanggal = models.DateField()
    jenis_servis = models.CharField(max_length=150, verbose_name="Jenis Servis")
    bengkel = models.CharField(max_length=150, blank=True, verbose_name="Bengkel / Tempat")
    biaya = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="Biaya (Rp)")
    keterangan = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Servis"
        verbose_name_plural = "Servis"
        ordering = ["-tanggal", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.jenis_servis} {self.tanggal:%d-%m-%Y}"
