from django.db import migrations, models


def _pilihan(field, choices, verbose_name, max_length, default):
    # Required columns; the one-off default only fills inspections saved
    # before this migration (there were none when it was written).
    return migrations.AddField(
        model_name="pemeriksaandiesel",
        name=field,
        field=models.CharField(choices=choices, default=default, max_length=max_length, verbose_name=verbose_name),
        preserve_default=False,
    )


YA_TIDAK = [("ya", "Ya"), ("tidak", "Tidak")]


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_pemeriksaan_diesel"),
    ]

    operations = [
        migrations.AddField(
            model_name="pemeriksaandiesel",
            name="km_mil",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Km / Mil"),
        ),
        _pilihan("km_berfungsi", YA_TIDAK, "Km / Mil Berfungsi", 5, "ya"),
        migrations.AddField(
            model_name="pemeriksaandiesel",
            name="jam_mesin",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Jam Mesin"),
        ),
        _pilihan("jam_mesin_berfungsi", YA_TIDAK, "Jam Mesin Berfungsi", 5, "ya"),
        _pilihan("buku_pemeliharaan", [("ada", "Ada"), ("tidak", "Tidak")], "Buku Pemeliharaan", 10, "ada"),
        _pilihan("kondisi_ranmor", [("jalan", "Jalan"), ("tidak", "Tidak")], "Kondisi Ranmor", 10, "jalan"),
        _pilihan("macam_pemeriksaan", [("tehnis", "Tehnis"), ("tiba_tiba", "Tiba-tiba")], "Macam Pemeriksaan", 20, "tehnis"),
    ]
