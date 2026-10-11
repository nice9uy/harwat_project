from django.db import migrations


def buat_baris(apps, schema_editor):
    """Jeep Diesel's Km / Mil is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="Km / Mil (Jeep Diesel)")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0043_km_jadwal_diesel"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
