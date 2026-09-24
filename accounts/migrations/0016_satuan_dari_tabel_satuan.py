import django.db.models.deletion
from django.db import migrations, models


def teks_ke_satuan(apps, schema_editor):
    """Turn the free-text satuan / kesatuan values into Satuan rows."""
    Satuan = apps.get_model("accounts", "Satuan")
    Laporan = apps.get_model("accounts", "Laporan")
    PemeriksaanGolonganB = apps.get_model("accounts", "PemeriksaanGolonganB")

    def satuan(nama):
        nama = (nama or "").strip() or "Tidak diketahui"
        return Satuan.objects.get_or_create(nama=nama)[0]

    for laporan in Laporan.objects.all():
        laporan.satuan_baru = satuan(laporan.satuan)
        laporan.save(update_fields=["satuan_baru"])
    for hasil in PemeriksaanGolonganB.objects.exclude(kesatuan=""):
        hasil.kesatuan_baru = satuan(hasil.kesatuan)
        hasil.save(update_fields=["kesatuan_baru"])


def satuan_ke_teks(apps, schema_editor):
    Laporan = apps.get_model("accounts", "Laporan")
    PemeriksaanGolonganB = apps.get_model("accounts", "PemeriksaanGolonganB")
    for laporan in Laporan.objects.select_related("satuan_baru"):
        laporan.satuan = laporan.satuan_baru.nama if laporan.satuan_baru else ""
        laporan.save(update_fields=["satuan"])
    for hasil in PemeriksaanGolonganB.objects.select_related("kesatuan_baru"):
        hasil.kesatuan = hasil.kesatuan_baru.nama if hasil.kesatuan_baru else ""
        hasil.save(update_fields=["kesatuan"])


class Migration(migrations.Migration):
    """Biodata Satuan and Golongan B Kesatuan now point at the Satuan table."""

    dependencies = [
        ("accounts", "0015_satuan"),
    ]

    operations = [
        migrations.AddField(
            model_name="laporan",
            name="satuan_baru",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="accounts.satuan"),
        ),
        migrations.AddField(
            model_name="pemeriksaangolonganb",
            name="kesatuan_baru",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="accounts.satuan"),
        ),
        migrations.RunPython(teks_ke_satuan, satuan_ke_teks),
        migrations.RemoveField(model_name="laporan", name="satuan"),
        migrations.RemoveField(model_name="pemeriksaangolonganb", name="kesatuan"),
        migrations.RenameField(model_name="laporan", old_name="satuan_baru", new_name="satuan"),
        migrations.RenameField(model_name="pemeriksaangolonganb", old_name="kesatuan_baru", new_name="kesatuan"),
        migrations.AlterField(
            model_name="laporan",
            name="satuan",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="biodata", to="accounts.satuan"),
        ),
        migrations.AlterField(
            model_name="pemeriksaangolonganb",
            name="kesatuan",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="pemeriksaan_golongan_b", to="accounts.satuan", verbose_name="Kesatuan",
            ),
        ),
    ]
