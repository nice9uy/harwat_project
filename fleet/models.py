import hashlib
import uuid

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
        KENDARAAN_BERMOTOR = "bermotor", "Motor"
        KENDARAAN_DIESEL = "diesel", "Kendaraan Diesel"
        JEEP_DIESEL = "jeep", "Jeep Diesel"
        # Kendaraan tempur and kendaraan taktis: listed and added like the
        # others. RANTIS has an inspection form, RANPUR none yet (accounts.golongan).
        RANPUR = "ranpur", "RANPUR"
        RANTIS = "rantis", "RANTIS"
        # Kendaraan khusus and kendaraan umum: listed and added like the
        # others. RANSUS has an inspection form (its equipment list), RANUM none yet.
        RANSUS = "ransus", "RANSUS"
        RANUM = "ranum", "RANUM"

    class Status(models.TextChoices):
        SIAP_PAKAI = "siap_pakai", "Siap Pakai"
        DALAM_PERBAIKAN = "dalam_perbaikan", "Dalam Perbaikan"
        PERLU_SERVIS = "perlu_servis", "Perlu Servis"

    class Kepemilikan(models.TextChoices):
        ORGANIK = "organik", "Organik"
        PINJAMAN = "pinjaman", "Pinjaman"

    group_kendaraan = models.CharField(
        max_length=10,
        choices=GroupKendaraan.choices,
        default=GroupKendaraan.GOLONGAN_B,
        db_index=True,
        verbose_name="Group Kendaraan",
    )
    nopol = models.CharField(max_length=20, unique=True, verbose_name="No. Registrasi")
    # Public id used in URLs and API responses instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    jenis = models.CharField(max_length=20, choices=Jenis.choices, blank=True)
    merek = models.CharField(max_length=100, verbose_name="Merk/Type")
    tahun = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Tahun")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SIAP_PAKAI)
    penanggung_jawab = models.CharField(max_length=150, blank=True, verbose_name="Penanggung Jawab")
    no_chasis = models.CharField(max_length=50, blank=True, verbose_name="No. Chasis")
    no_mesin = models.CharField(max_length=50, blank=True, verbose_name="No. Mesin")
    # Whose it is: the unit's own (organik) or on loan (pinjaman). Vehicles
    # added before this column existed count as organik.
    kepemilikan = models.CharField(
        max_length=10, choices=Kepemilikan.choices, default=Kepemilikan.ORGANIK, verbose_name="Status",
    )
    # The matra picked on Form Tambah (accounts.roles.MATRA). Empty for
    # vehicles added before this column existed or outside Form Tambah.
    matra = models.CharField(
        max_length=10, choices=[("darat", "Matra Darat"), ("laut", "Matra Laut"), ("udara", "Matra Udara")],
        blank=True, db_index=True, verbose_name="Matra",
    )
    # Empty for vehicles added before this column existed.
    dibuat_pada = models.DateTimeField(auto_now_add=True, null=True, verbose_name="Ditambahkan pada")
    # Who added it: the account, and (via Form Tambah) the biodata entered
    # there. Empty for vehicles added before these columns existed.
    ditambahkan_oleh = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="kendaraan_ditambahkan",
        verbose_name="Ditambahkan oleh",
    )
    penambah = models.ForeignKey(
        "accounts.Laporan", on_delete=models.SET_NULL, null=True, blank=True, related_name="kendaraan_ditambahkan",
        verbose_name="Biodata Penambah",
    )

    class Meta:
        ordering = ["nopol"]
        indexes = [models.Index(fields=["group_kendaraan", "nopol"], name="vehicle_group_nopol_idx")]

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

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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


class NonKendaraan(models.Model):
    """An inventory item that isn't a vehicle, listed on the Non Kendaraan menu."""

    class Group(models.TextChoices):
        """The tabs of the Non Kendaraan page."""

        TENDA = "tenda", "Tenda"

    class Kondisi(models.TextChoices):
        BAIK = "B", "Baik"
        RUSAK_RINGAN = "RR", "Rusak Ringan"
        RUSAK_BERAT = "RB", "Rusak Berat"

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    group = models.CharField(max_length=20, choices=Group.choices, default=Group.TENDA, db_index=True)
    # Empty for the groups whose form doesn't ask for it (see
    # accounts.non_kendaraan.KOLOM); NULL so those rows don't clash on unique.
    kode_barang = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="Kode Barang")
    nama_barang = models.CharField(max_length=150, verbose_name="Nama Barang")
    merek = models.CharField(max_length=100, blank=True, verbose_name="Merk/Type")
    no_seri = models.CharField(max_length=100, blank=True, verbose_name="No. Seri")
    jumlah = models.PositiveIntegerField(default=1)
    satuan = models.CharField(max_length=30, default="unit")
    kondisi = models.CharField(max_length=2, choices=Kondisi.choices, default=Kondisi.BAIK)
    foto = models.ImageField(upload_to="non_kendaraan/", blank=True, max_length=255)
    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Ditambahkan pada")
    ditambahkan_oleh = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="non_kendaraan_ditambahkan",
        verbose_name="Ditambahkan oleh",
    )

    class Meta:
        verbose_name = "Non Kendaraan"
        verbose_name_plural = "Non Kendaraan"
        ordering = ["kode_barang", "nama_barang", "id"]

    def __str__(self):
        return f"{self.kode_barang} — {self.nama_barang}" if self.kode_barang else self.nama_barang
