from django.db import models


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

    def __str__(self):
        return f"{self.nama} ({self.nip})"
