from django.db import migrations


def buat_baris(apps, schema_editor):
    """Golongan B's KM Kendaraan is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="KM Kendaraan")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0041_km_jadwal"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
