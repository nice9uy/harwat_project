from django.core.validators import MaxValueValidator
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

    def ringkasan(self):
        parts = [
            f"Kelas {self.pembagian_kelas}",
            f"Eselon {self.eselon_reparasi}",
            self.get_macam_pemeriksaan_display(),
            f"Buku jalan {self.get_buku_jalan_display().lower()}",
        ]
        if self.kesatuan:
            parts.append(self.kesatuan)
        return " · ".join(parts)


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


class PerbaikanGolonganB(models.Model):
    """A repair of one damaged part (RR/RB) found in a Golongan B inspection.

    The part drops off the to-repair list once its latest repair has
    kondisi B (Baik).
    """

    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_golongan_b",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanGolonganBItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(max_length=2, choices=checklist.KONDISI)
    jumlah = models.PositiveIntegerField(null=True, blank=True)
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Golongan B"
        verbose_name_plural = "Perbaikan Golongan B"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class PemeriksaanBermotor(models.Model):
    """One inspection of a Kendaraan Bermotor vehicle (63-component paper form)."""

    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_bermotor",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_bermotor",
        verbose_name="Kendaraan",
    )
    bbm = models.CharField(max_length=100, blank=True, verbose_name="BBM")
    buku_harian = models.CharField(max_length=10, choices=checklist.BUKU_HARIAN, verbose_name="Buku Harian")
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    tempat_pemeriksaan = models.CharField(max_length=150, blank=True, verbose_name="Tempat Pemeriksaan")
    ukuran_ban = models.CharField(max_length=50, blank=True, verbose_name="Ukuran Ban")
    # Tyre condition in percent (0-100), as on the paper form's "Ban Uk." table.
    ban_depan_kiri = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Ban Depan Kiri (%)",
    )
    ban_depan_kanan = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Ban Depan Kanan (%)",
    )
    ban_belakang_kiri = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Ban Belakang Kiri (%)",
    )
    ban_belakang_kanan = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Ban Belakang Kanan (%)",
    )
    ban_cadangan = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Ban Cadangan (%)",
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    BAN_FIELDS = [
        ("ban_depan_kiri", "Depan Kiri"),
        ("ban_depan_kanan", "Depan Kanan"),
        ("ban_belakang_kiri", "Belakang Kiri"),
        ("ban_belakang_kanan", "Belakang Kanan"),
        ("ban_cadangan", "Cadangan"),
    ]

    class Meta:
        verbose_name = "Pemeriksaan Kendaraan Bermotor"
        verbose_name_plural = "Pemeriksaan Kendaraan Bermotor"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"

    def ringkasan(self):
        parts = [
            self.get_macam_pemeriksaan_display(),
            f"Buku harian {self.get_buku_harian_display().lower()}",
        ]
        if self.bbm:
            parts.append(f"BBM {self.bbm}")
        if self.tempat_pemeriksaan:
            parts.append(self.tempat_pemeriksaan)
        ban = [f"{label} {getattr(self, field)}%" for field, label in self.BAN_FIELDS if getattr(self, field) is not None]
        if self.ukuran_ban or ban:
            parts.append(" ".join(filter(None, [f"Ban {self.ukuran_ban}".strip(), ", ".join(ban)])))
        return " · ".join(parts)


class PemeriksaanBermotorItem(models.Model):
    """One of the 63 checked components of a PemeriksaanBermotor."""

    pemeriksaan = models.ForeignKey(PemeriksaanBermotor, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    kondisi = models.CharField(max_length=2, choices=checklist.KONDISI_BERMOTOR)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan Kendaraan Bermotor"
        verbose_name_plural = "Item Pemeriksaan Kendaraan Bermotor"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_bermotor"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanBermotor(models.Model):
    """A repair of one component that wasn't Baik in a Kendaraan Bermotor inspection."""

    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_bermotor",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanBermotorItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(max_length=2, choices=checklist.KONDISI_BERMOTOR)
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Kendaraan Bermotor"
        verbose_name_plural = "Perbaikan Kendaraan Bermotor"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"
