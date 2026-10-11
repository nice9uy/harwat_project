from django.db import migrations


def buat_baris(apps, schema_editor):
    """RANTIS's Km / Mil is marked * too: its row for Pengaturan > KM."""
    apps.get_model("accounts", "KmJadwal").objects.get_or_create(komponen="Km / Mil (RANTIS)")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0056_rantis"),
    ]

    operations = [
        migrations.RunPython(buat_baris, migrations.RunPython.noop),
    ]
