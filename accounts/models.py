from django.db import models

from . import pemeriksaan as checklist


class RevokedToken(models.Model):
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class Laporan(models.Model):
    nip = models.CharField(max_length=32, verbose_name="NIP")
    nama = models.CharField(max_length=150)
    pangkat = models.CharField(max_length=100)
    jabatan = models.CharField(max_length=150)
    satuan = models.CharField(max_length=150)
    foto = models.ImageField(upload_to="laporan/")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Biodata Pemeriksa"
        verbose_name_plural = "Biodata Pemeriksa"

    def __str__(self):
        return f"{self.nama} ({self.nip})"


class PemeriksaanGolonganB(models.Model):
    """One inspection of a Golongan B vehicle, filled in on Form Pemeriksaan."""

    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_golongan_b",
        verbose_name="Biodata Pemeriksa",
    )
    # PROTECT: inspection history must not vanish when a vehicle is deleted.
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_golongan_b",
        verbose_name="Kendaraan",
    )
    pembagian_kelas = models.CharField(
        max_length=1, choices=[(k, k) for k in checklist.PEMBAGIAN_KELAS], verbose_name="Pembagian Kelas",
    )
    eselon_reparasi = models.CharField(
        max_length=1, choices=[(e, e) for e in checklist.ESELON_REPARASI], verbose_name="Eselon Reparasi",
    )
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    buku_jalan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, verbose_name="Buku Jalan")
    kesatuan = models.CharField(max_length=150, blank=True, verbose_name="Kesatuan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pemeriksaan Golongan B"
        verbose_name_plural = "Pemeriksaan Golongan B"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"


class PemeriksaanGolonganBItem(models.Model):
    """One of the 40 checked parts (Motor … Cat) of a PemeriksaanGolonganB."""

    pemeriksaan = models.ForeignKey(PemeriksaanGolonganB, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Alat")
    jumlah = models.PositiveIntegerField(null=True, blank=True)
    kondisi = models.CharField(max_length=2, choices=checklist.KONDISI)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan Golongan B"
        verbose_name_plural = "Item Pemeriksaan Golongan B"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"
