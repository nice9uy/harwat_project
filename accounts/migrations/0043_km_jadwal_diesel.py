from django.db import migrations


def buat_baris(apps, schema_editor):
    """Kendaraan Diesel's Km / Mil is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="Km / Mil (Kendaraan Diesel)")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0042_km_jadwal_golongan_b"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
