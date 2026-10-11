from django.db import migrations


def buat_baris(apps, schema_editor):
    """Kendaraan Bermotor's KM Kendaraan is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="KM Kendaraan (Kendaraan Bermotor)")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0046_bermotor_km"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
