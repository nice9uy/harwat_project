import uuid

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from treebeard.mp_tree import MP_Node

from . import pemeriksaan as checklist
from . import roles


class RevokedToken(models.Model):
    jti = models.CharField(max_length=255, unique=True, db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


# Up to MAKS_FOTO photos per checked or repaired part, in these fields.
FOTO_FIELDS = ["foto", "foto_2", "foto_3", "foto_4"]
MAKS_FOTO = len(FOTO_FIELDS)


class FotoMixin:
    """For models with the FOTO_FIELDS photo columns."""

    @property
    def daftar_foto(self):
        """The photos that are set, in order."""
        return [f for f in (getattr(self, nama) for nama in FOTO_FIELDS) if f]

    @staticmethod
    def kolom_foto(files):
        """``{field: file}`` for up to MAKS_FOTO files, to pass to create()."""
        return dict(zip(FOTO_FIELDS, files))


class Laporan(models.Model):
    class TipeIdentitas(models.TextChoices):
        PNS = "PNS", "PNS"
        TNI = "TNI", "TNI"

    tipe_identitas = models.CharField(
        max_length=3, choices=TipeIdentitas.choices, default=TipeIdentitas.TNI,
        verbose_name="Tipe Identitas",
    )
    nip = models.CharField(max_length=32, verbose_name="NIP")
    nama = models.CharField(max_length=150)
    pangkat = models.CharField(max_length=100)
    jabatan = models.CharField(max_length=150)
    satuan = models.ForeignKey("Satuan", on_delete=models.PROTECT, related_name="biodata")
    foto = models.ImageField(upload_to="laporan/", max_length=500)
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    # The account that submitted this biodata (with an inspection, repair or
    # new vehicle): ties the activity to a team member for Laporan Tim.
    # Empty for biodata saved before this column existed.
    akun = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="biodata", verbose_name="Akun",
    )

    class Meta:
        verbose_name = "Biodata Pemeriksa"
        verbose_name_plural = "Biodata Pemeriksa"

    @property
    def label_nip(self):
        return "NRP" if self.tipe_identitas == self.TipeIdentitas.TNI else "NIP"

    def __str__(self):
        return f"{self.nama} ({self.nip})"


class PemeriksaanGolonganB(models.Model):
    """One inspection of a Golongan B vehicle, filled in on Form Pemeriksaan."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    # No longer asked on the form; kept (and shown) for the inspections that have it.
    buku_jalan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, blank=True, verbose_name="Buku Jalan")
    # Odometer reading at the inspection, with a photo of it as proof.
    km_kendaraan = models.PositiveIntegerField(null=True, blank=True, verbose_name="KM Kendaraan")
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto KM Kendaraan")
    kesatuan = models.ForeignKey(
        "Satuan", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pemeriksaan_golongan_b", verbose_name="Kesatuan",
    )
    # Keadaan Ban: condition of tyres 1-8 in percent, as on the paper form.
    ban_1 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 1 (%)",
    )
    ban_2 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 2 (%)",
    )
    ban_3 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 3 (%)",
    )
    ban_4 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 4 (%)",
    )
    ban_5 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 5 (%)",
    )
    ban_6 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 6 (%)",
    )
    ban_7 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 7 (%)",
    )
    ban_8 = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)], verbose_name="Keadaan Ban 8 (%)",
    )
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    BAN_FIELDS = [f"ban_{i}" for i in range(1, 9)]

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
        ]
        if self.buku_jalan:
            parts.append(f"Buku jalan {self.get_buku_jalan_display().lower()}")
        if self.km_kendaraan is not None:
            parts.append(f"KM {self.km_kendaraan}")
        if self.kesatuan:
            parts.append(self.kesatuan.nama)
        ban = [f"{i} {getattr(self, f)}%" for i, f in enumerate(self.BAN_FIELDS, start=1) if getattr(self, f) is not None]
        if ban:
            parts.append("Ban " + ", ".join(ban))
        return " · ".join(parts)


class PemeriksaanGolonganBItem(FotoMixin, models.Model):
    """One of the 40 checked parts (Motor … Cat) of a PemeriksaanGolonganB."""

    pemeriksaan = models.ForeignKey(PemeriksaanGolonganB, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Alat")
    jumlah = models.PositiveIntegerField(null=True, blank=True)
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
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


class PerbaikanGolonganB(FotoMixin, models.Model):
    """A repair of one damaged part (RR/RB) found in a Golongan B inspection.

    The part drops off the to-repair list once its latest repair has
    kondisi B (Baik).
    """

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_golongan_b",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanGolonganBItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    jumlah = models.PositiveIntegerField(null=True, blank=True)
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Golongan B"
        verbose_name_plural = "Perbaikan Golongan B"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class PemeriksaanBermotor(models.Model):
    """One inspection of a Motor vehicle (62 components)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_bermotor",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_bermotor",
        verbose_name="Kendaraan",
    )
    bbm = models.CharField(max_length=100, blank=True, verbose_name="BBM")
    # Odometer reading at the inspection, with a photo of it as proof.
    km_kendaraan = models.PositiveIntegerField(null=True, blank=True, verbose_name="KM Kendaraan")
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto KM Kendaraan")
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
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    BAN_FIELDS = [
        ("ban_depan_kiri", "Depan Kiri"),
        ("ban_depan_kanan", "Depan Kanan"),
        ("ban_belakang_kiri", "Belakang Kiri"),
        ("ban_belakang_kanan", "Belakang Kanan"),
        ("ban_cadangan", "Cadangan"),
    ]

    class Meta:
        verbose_name = "Pemeriksaan Motor"
        verbose_name_plural = "Pemeriksaan Motor"
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
        if self.km_kendaraan is not None:
            parts.append(f"KM {self.km_kendaraan}")
        if self.tempat_pemeriksaan:
            parts.append(self.tempat_pemeriksaan)
        ban = [f"{label} {getattr(self, field)}%" for field, label in self.BAN_FIELDS if getattr(self, field) is not None]
        if self.ukuran_ban or ban:
            parts.append(" ".join(filter(None, [f"Ban {self.ukuran_ban}".strip(), ", ".join(ban)])))
        return " · ".join(parts)


class PemeriksaanBermotorItem(FotoMixin, models.Model):
    """One of the checked components of a PemeriksaanBermotor."""

    pemeriksaan = models.ForeignKey(PemeriksaanBermotor, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI_BERMOTOR)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan Motor"
        verbose_name_plural = "Item Pemeriksaan Motor"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_bermotor"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanBermotor(FotoMixin, models.Model):
    """A repair of one component that wasn't Baik in a Motor inspection."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_bermotor",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanBermotorItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Motor"
        verbose_name_plural = "Perbaikan Motor"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class Anggota(MP_Node):
    """Team hierarchy: each Ketua Tim is a root, their Tim members are children.

    Only Ketua Tim and Tim users are in the tree; other roles aren't.
    """

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="anggota")
    # On a Ketua Tim (root) only: the Admin that added them and so manages
    # them and their members. Empty for a Ketua Tim made elsewhere.
    # PROTECT: an Admin with Ketua Tim isn't deleted (the Pengaturan delete
    # view says so first).
    admin = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True, related_name="ketua_tim_list",
        verbose_name="Admin",
    )

    class Meta:
        verbose_name = "Anggota Tim"
        verbose_name_plural = "Anggota Tim"

    def __str__(self):
        return self.user.username



class PemeriksaanDiesel(models.Model):
    """One inspection of a Kendaraan Diesel (paper form grouped by system, 141 parts)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_diesel",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_diesel",
        verbose_name="Kendaraan",
    )
    km_mil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Km / Mil")
    # A photo of the odometer, as proof of the reading.
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto Km / Mil")
    km_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Km / Mil Berfungsi")
    jam_mesin = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jam Mesin")
    jam_mesin_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Jam Mesin Berfungsi")
    buku_pemeliharaan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, verbose_name="Buku Pemeliharaan")
    kondisi_ranmor = models.CharField(max_length=10, choices=checklist.KONDISI_RANMOR, verbose_name="Kondisi Ranmor")
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pemeriksaan Kendaraan Diesel"
        verbose_name_plural = "Pemeriksaan Kendaraan Diesel"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"

    def ringkasan(self):
        km = f"{self.km_mil} km" if self.km_mil is not None else "Km -"
        jam = f"{self.jam_mesin} jam" if self.jam_mesin is not None else "Jam mesin -"
        return " · ".join([
            self.get_macam_pemeriksaan_display(),
            f"{km} ({'berfungsi' if self.km_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"{jam} ({'berfungsi' if self.jam_mesin_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"Buku pemeliharaan {self.get_buku_pemeliharaan_display().lower()}",
            f"Ranmor {self.get_kondisi_ranmor_display().lower()}",
        ])


class PemeriksaanDieselItem(FotoMixin, models.Model):
    """One checked part of a PemeriksaanDiesel: satuan, jumlah riil/nyata, kondisi."""

    pemeriksaan = models.ForeignKey(PemeriksaanDiesel, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    satuan = models.CharField(max_length=30, blank=True)
    jumlah_riil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Riil")
    jumlah_nyata = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Nyata")
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI_DIESEL)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan Kendaraan Diesel"
        verbose_name_plural = "Item Pemeriksaan Kendaraan Diesel"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_diesel"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanDiesel(FotoMixin, models.Model):
    """A repair of one part of a Kendaraan Diesel inspection that needed it."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_diesel",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanDieselItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Kendaraan Diesel"
        verbose_name_plural = "Perbaikan Kendaraan Diesel"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class PemeriksaanJeepDiesel(models.Model):
    """One inspection of a Jeep Diesel (same paper layout as Kendaraan Diesel, 112 parts)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_jeep_diesel",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_jeep_diesel",
        verbose_name="Kendaraan",
    )
    km_mil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Km / Mil")
    # A photo of the odometer, as proof of the reading.
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto Km / Mil")
    km_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Km / Mil Berfungsi")
    jam_mesin = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jam Mesin")
    jam_mesin_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Jam Mesin Berfungsi")
    buku_pemeliharaan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, verbose_name="Buku Pemeliharaan")
    kondisi_ranmor = models.CharField(max_length=10, choices=checklist.KONDISI_RANMOR, verbose_name="Kondisi Ranmor")
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pemeriksaan Jeep Diesel"
        verbose_name_plural = "Pemeriksaan Jeep Diesel"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"

    def ringkasan(self):
        km = f"{self.km_mil} km" if self.km_mil is not None else "Km -"
        jam = f"{self.jam_mesin} jam" if self.jam_mesin is not None else "Jam mesin -"
        return " · ".join([
            self.get_macam_pemeriksaan_display(),
            f"{km} ({'berfungsi' if self.km_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"{jam} ({'berfungsi' if self.jam_mesin_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"Buku pemeliharaan {self.get_buku_pemeliharaan_display().lower()}",
            f"Ranmor {self.get_kondisi_ranmor_display().lower()}",
        ])


class PemeriksaanJeepDieselItem(FotoMixin, models.Model):
    """One checked part of a PemeriksaanJeepDiesel: satuan, jumlah riil/nyata, kondisi."""

    pemeriksaan = models.ForeignKey(PemeriksaanJeepDiesel, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    satuan = models.CharField(max_length=30, blank=True)
    jumlah_riil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Riil")
    jumlah_nyata = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Nyata")
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI_JEEP_DIESEL)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan Jeep Diesel"
        verbose_name_plural = "Item Pemeriksaan Jeep Diesel"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_jeep_diesel"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanJeepDiesel(FotoMixin, models.Model):
    """A repair of one part of a Jeep Diesel inspection that needed it."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_jeep_diesel",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanJeepDieselItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan Jeep Diesel"
        verbose_name_plural = "Perbaikan Jeep Diesel"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class PemeriksaanRantis(models.Model):
    """One inspection of a RANTIS (same paper layout as Kendaraan Diesel, 116 parts)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_rantis",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_rantis",
        verbose_name="Kendaraan",
    )
    km_mil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Km / Mil")
    # A photo of the odometer, as proof of the reading.
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto Km / Mil")
    km_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Km / Mil Berfungsi")
    jam_mesin = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jam Mesin")
    jam_mesin_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Jam Mesin Berfungsi")
    buku_pemeliharaan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, verbose_name="Buku Pemeliharaan")
    kondisi_ranmor = models.CharField(max_length=10, choices=checklist.KONDISI_RANMOR, verbose_name="Kondisi Ranmor")
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pemeriksaan RANTIS"
        verbose_name_plural = "Pemeriksaan RANTIS"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"

    def ringkasan(self):
        km = f"{self.km_mil} km" if self.km_mil is not None else "Km -"
        jam = f"{self.jam_mesin} jam" if self.jam_mesin is not None else "Jam mesin -"
        return " · ".join([
            self.get_macam_pemeriksaan_display(),
            f"{km} ({'berfungsi' if self.km_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"{jam} ({'berfungsi' if self.jam_mesin_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"Buku pemeliharaan {self.get_buku_pemeliharaan_display().lower()}",
            f"Ranmor {self.get_kondisi_ranmor_display().lower()}",
        ])


class PemeriksaanRantisItem(FotoMixin, models.Model):
    """One checked part of a PemeriksaanRantis: satuan, jumlah riil/nyata, kondisi."""

    pemeriksaan = models.ForeignKey(PemeriksaanRantis, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    satuan = models.CharField(max_length=30, blank=True)
    jumlah_riil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Riil")
    jumlah_nyata = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Nyata")
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI_RANTIS)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan RANTIS"
        verbose_name_plural = "Item Pemeriksaan RANTIS"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_rantis"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanRantis(FotoMixin, models.Model):
    """A repair of one part of a RANTIS inspection that needed it."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_rantis",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanRantisItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan RANTIS"
        verbose_name_plural = "Perbaikan RANTIS"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"


class PemeriksaanRansus(models.Model):
    """One inspection of a RANSUS (the header of Kendaraan Diesel, 40 pieces of equipment)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pemeriksa = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="pemeriksaan_ransus",
        verbose_name="Biodata Pemeriksa",
    )
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.PROTECT, related_name="pemeriksaan_ransus",
        verbose_name="Kendaraan",
    )
    km_mil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Km / Mil")
    # A photo of the odometer, as proof of the reading.
    foto_km = models.ImageField(upload_to="pemeriksaan/", blank=True, max_length=255, verbose_name="Foto Km / Mil")
    km_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Km / Mil Berfungsi")
    jam_mesin = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jam Mesin")
    jam_mesin_berfungsi = models.CharField(max_length=5, choices=checklist.YA_TIDAK, verbose_name="Jam Mesin Berfungsi")
    buku_pemeliharaan = models.CharField(max_length=10, choices=checklist.BUKU_JALAN, verbose_name="Buku Pemeliharaan")
    kondisi_ranmor = models.CharField(max_length=10, choices=checklist.KONDISI_RANMOR, verbose_name="Kondisi Ranmor")
    macam_pemeriksaan = models.CharField(
        max_length=20, choices=checklist.MACAM_PEMERIKSAAN, verbose_name="Macam Pemeriksaan",
    )
    kesimpulan = models.CharField(
        max_length=20, choices=checklist.KESIMPULAN, default="siap_pakai", verbose_name="Kesimpulan",
    )
    keterangan = models.TextField(blank=True, verbose_name="Keterangan")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pemeriksaan RANSUS"
        verbose_name_plural = "Pemeriksaan RANSUS"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"

    def ringkasan(self):
        km = f"{self.km_mil} km" if self.km_mil is not None else "Km -"
        jam = f"{self.jam_mesin} jam" if self.jam_mesin is not None else "Jam mesin -"
        return " · ".join([
            self.get_macam_pemeriksaan_display(),
            f"{km} ({'berfungsi' if self.km_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"{jam} ({'berfungsi' if self.jam_mesin_berfungsi == 'ya' else 'tidak berfungsi'})",
            f"Buku pemeliharaan {self.get_buku_pemeliharaan_display().lower()}",
            f"Ranmor {self.get_kondisi_ranmor_display().lower()}",
        ])


class PemeriksaanRansusItem(FotoMixin, models.Model):
    """One checked part of a PemeriksaanRansus: satuan, jumlah riil/nyata, kondisi."""

    pemeriksaan = models.ForeignKey(PemeriksaanRansus, on_delete=models.CASCADE, related_name="items")
    nomor = models.PositiveSmallIntegerField()
    nama_alat = models.CharField(max_length=100, verbose_name="Nama Komponen")
    satuan = models.CharField(max_length=30, blank=True)
    jumlah_riil = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Riil")
    jumlah_nyata = models.PositiveIntegerField(null=True, blank=True, verbose_name="Jumlah Nyata")
    kondisi = models.CharField(max_length=3, choices=checklist.KONDISI_RANSUS)
    foto = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_2 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_3 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    foto_4 = models.ImageField(upload_to="pemeriksaan/", blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        verbose_name = "Item Pemeriksaan RANSUS"
        verbose_name_plural = "Item Pemeriksaan RANSUS"
        ordering = ["nomor"]
        constraints = [
            models.UniqueConstraint(fields=["pemeriksaan", "nomor"], name="unique_item_per_pemeriksaan_ransus"),
        ]

    def __str__(self):
        return f"{self.nomor}. {self.nama_alat}"


class PerbaikanRansus(FotoMixin, models.Model):
    """A repair of one part of a RANSUS inspection that needed it."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    teknisi = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="perbaikan_ransus",
        verbose_name="Biodata Teknisi",
    )
    item = models.ForeignKey(
        PemeriksaanRansusItem, on_delete=models.CASCADE, related_name="perbaikan",
        verbose_name="Item Pemeriksaan",
    )
    kondisi = models.CharField(
        max_length=3, choices=checklist.KONDISI_PERBAIKAN + checklist.KONDISI_PERBAIKAN_LAMA,
    )
    keterangan = models.TextField(blank=True)
    foto = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_2 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_3 = models.ImageField(upload_to="perbaikan/", blank=True)
    foto_4 = models.ImageField(upload_to="perbaikan/", blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perbaikan RANSUS"
        verbose_name_plural = "Perbaikan RANSUS"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.item.pemeriksaan.vehicle.nopol} — {self.item} ({self.kondisi})"



class KendaraanRusak(FotoMixin, models.Model):
    """A vehicle declared Rusak / Tidak Layak Pakai with the form of that
    name: why, and up to four photos. It makes the vehicle Rusak Berat until
    an inspection made after it says otherwise (golongan.status_kendaraan)."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    vehicle = models.ForeignKey("fleet.Vehicle", on_delete=models.CASCADE, related_name="rusak", verbose_name="Kendaraan")
    pelapor = models.ForeignKey(
        Laporan, on_delete=models.CASCADE, related_name="kendaraan_rusak", verbose_name="Biodata Pelapor",
    )
    alasan = models.TextField(verbose_name="Alasan / Keterangan Kerusakan")
    foto = models.ImageField(upload_to="rusak/", blank=True, max_length=255)
    foto_2 = models.ImageField(upload_to="rusak/", blank=True, max_length=255)
    foto_3 = models.ImageField(upload_to="rusak/", blank=True, max_length=255)
    foto_4 = models.ImageField(upload_to="rusak/", blank=True, max_length=255)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kendaraan Rusak/Tidak Layak Pakai"
        verbose_name_plural = "Kendaraan Rusak/Tidak Layak Pakai"
        ordering = ["-dibuat_pada", "-id"]

    def __str__(self):
        return f"{self.vehicle.nopol} — {self.dibuat_pada:%d-%m-%Y}"


class VpnPeer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vpn_peer")
    peer_name = models.CharField(max_length=50, verbose_name="Nama Peer")
    private_key = models.TextField(blank=True, verbose_name="Private Key")
    public_key = models.TextField(blank=True, verbose_name="Public Key")
    # Left empty, save() takes the next free address of settings.VPN_SUBNET.
    client_ip = models.CharField(max_length=50, blank=True, unique=True, verbose_name="IP Client (CIDR)")
    preshared_key = models.TextField(blank=True, verbose_name="Preshared Key")

    class Meta:
        verbose_name = "VPN Peer"
        verbose_name_plural = "VPN Peer"

    def __str__(self):
        return f"{self.user.username} — {self.peer_name}"

    def save(self, *args, **kwargs):
        if self.client_ip:
            return super().save(*args, **kwargs)
        from .vpn_utils import ip_bebas
        # Two peers saved at once can pick the same address; the unique
        # constraint turns the loser away and it picks again.
        for sisa in range(4, -1, -1):
            self.client_ip = ip_bebas()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                self.client_ip = ""
                if not sisa:
                    raise

    def wireguard_config(self, server_endpoint, server_pubkey, dns="", allowed_ips="0.0.0.0/0, ::/0"):
        lines = ["[Interface]", f"PrivateKey = {self.private_key}"]
        if self.client_ip:
            lines.append(f"Address = {self.client_ip}")
        if dns:
            lines.append(f"DNS = {dns}")
        lines += ["", "[Peer]", f"PublicKey = {server_pubkey}"]
        if self.preshared_key:
            lines.append(f"PresharedKey = {self.preshared_key}")
        lines += [f"Endpoint = {server_endpoint}", f"AllowedIPs = {allowed_ips}", "PersistentKeepalive = 25"]
        return "\n".join(lines)


class Satuan(models.Model):
    """Military/organisational unit (satuan), managed under Pengaturan."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nama = models.CharField(max_length=150, unique=True, verbose_name="Nama Satuan")
    # Which Pengaturan > Satuan tab it is listed on (roles.MATRA). The units
    # there before this column are the army's, so Darat.
    matra = models.CharField(max_length=10, choices=roles.MATRA, default="darat", db_index=True, verbose_name="Matra")
    keterangan = models.TextField(blank=True)
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Satuan"
        verbose_name_plural = "Satuan"
        ordering = ["nama"]

    def __str__(self):
        return self.nama


class DraftPemeriksaan(models.Model):
    """Temporary auto-saved draft of a pemeriksaan form (non-file fields only).

    Deleted automatically when the inspection is successfully submitted.
    Resumable by scanning the same vehicle's QR code.
    """

    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.CASCADE, related_name="draft_pemeriksaan"
    )
    pemeriksa = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="draft_pemeriksaan"
    )
    data = models.JSONField(default=dict)
    diperbarui_pada = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("vehicle", "pemeriksa")]
        verbose_name = "Draft Pemeriksaan"
        verbose_name_plural = "Draft Pemeriksaan"

    def __str__(self):
        return f"Draft {self.vehicle.nopol} — {self.pemeriksa.get_full_name() or self.pemeriksa.username}"


class DraftPerbaikan(models.Model):
    """Auto-saved draft of Form Perbaikan for one vehicle and technician
    (the fields that aren't files), written every few seconds while the form
    is open. Deleted when the repair is saved or cancelled; reopening the
    vehicle fills the form back in."""

    vehicle = models.ForeignKey("fleet.Vehicle", on_delete=models.CASCADE, related_name="draft_perbaikan")
    teknisi = models.ForeignKey(User, on_delete=models.CASCADE, related_name="draft_perbaikan")
    data = models.JSONField(default=dict)
    diperbarui_pada = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("vehicle", "teknisi")]
        verbose_name = "Draft Perbaikan"
        verbose_name_plural = "Draft Perbaikan"

    def __str__(self):
        return f"Draft perbaikan {self.vehicle.nopol} — {self.teknisi.username}"


class AkunPublik(models.Model):
    """What auth.User can't hold (it takes no extra columns): the public
    UUID used in URLs instead of the guessable user pk, and an Admin's matra.
    Created for every new user by the post_save signal in apps.py."""

    class Matra(models.TextChoices):
        DARAT = "darat", "Matra Darat"
        LAUT = "laut", "Matra Laut"
        UDARA = "udara", "Matra Udara"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="publik")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Set for an Admin only (picked in Tambah User / Edit); empty otherwise.
    matra = models.CharField(max_length=10, choices=Matra.choices, blank=True, verbose_name="Matra")
    # The unit the account belongs to, picked in Tambah User / Edit (typed,
    # with suggestions). Empty for accounts made before it was asked for.
    satuan = models.ForeignKey(
        "Satuan", on_delete=models.SET_NULL, null=True, blank=True, related_name="akun", verbose_name="Satuan",
    )

    class Meta:
        verbose_name = "UUID Akun"
        verbose_name_plural = "UUID Akun"

    def __str__(self):
        return f"{self.user.username} ({self.uuid})"

class AksesFormTambah(models.Model):
    """Which Form Tambah forms a Tim Penambahan Data member may open
    (roles.FORM_TAMBAH keys), set by a superuser in Form Group. A member
    without a row may open all of them."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="akses_form_tambah")
    form = models.JSONField(default=list)

    class Meta:
        verbose_name = "Akses Form Tambah"
        verbose_name_plural = "Akses Form Tambah"

    def __str__(self):
        return self.user.username


class BawahanPimpinan(models.Model):
    """A Ketua Tim a Pimpinan Tim has picked as under them: the Pimpinan Tim
    sees that team's work (dashboard, Anggota Tim, Laporan Tim). A Ketua Tim
    can be under several Pimpinan Tim."""

    pimpinan = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bawahan_ketua", verbose_name="Pimpinan Ketua Tim")
    ketua = models.ForeignKey(Anggota, on_delete=models.CASCADE, related_name="pimpinan_tim", verbose_name="Ketua Tim")

    class Meta:
        verbose_name = "Bawahan Pimpinan Ketua Tim"
        verbose_name_plural = "Bawahan Pimpinan Ketua Tim"
        constraints = [models.UniqueConstraint(fields=["pimpinan", "ketua"], name="unique_bawahan_pimpinan")]

    def __str__(self):
        return f"{self.pimpinan.username} — {self.ketua.user.username}"


class PekerjaanAktif(models.Model):
    """A repair or an addition a Tim member has started and not saved yet,
    shown on their Status menu (which can cancel it). An inspection in
    progress is a DraftPemeriksaan instead."""

    class Jenis(models.TextChoices):
        PERBAIKAN = "perbaikan", "Perbaikan"
        PENAMBAHAN = "penambahan", "Penambahan Data"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pekerjaan_aktif")
    jenis = models.CharField(max_length=20, choices=Jenis.choices)
    # The vehicle being repaired; empty for an addition (no vehicle yet).
    vehicle = models.ForeignKey(
        "fleet.Vehicle", on_delete=models.CASCADE, null=True, blank=True, related_name="pekerjaan_aktif",
    )
    keterangan = models.CharField(max_length=100, blank=True)
    dimulai_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pekerjaan Aktif"
        verbose_name_plural = "Pekerjaan Aktif"

    def __str__(self):
        return f"{self.user.username} — {self.get_jenis_display()}"


class KmJadwal(models.Model):
    """Pengaturan > KM: for a part marked * on the inspection form
    (checklist.KOMPONEN_BERMOTOR_KM), every how many km and every how many
    months it is due a check."""

    # Public id used in URLs instead of the guessable pk.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    komponen = models.CharField(max_length=100, unique=True)
    # Empty until an admin sets it.
    interval_km = models.PositiveIntegerField(null=True, blank=True, verbose_name="Interval KM")
    # Waktu Servis: every how many months it is due, whatever the km. Empty until set.
    interval_bulan = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Waktu Servis (bulan)")
    diperbarui_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "KM Jadwal"
        verbose_name_plural = "KM Jadwal"
        ordering = ["komponen"]

    def __str__(self):
        return self.komponen
