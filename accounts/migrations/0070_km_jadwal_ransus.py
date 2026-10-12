from django.db import migrations


def buat_baris(apps, schema_editor):
    """RANSUS's Km / Mil is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="Km / Mil (RANSUS)")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0069_ransus"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
