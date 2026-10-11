from django.db import migrations


def buat_group(apps, schema_editor):
    """The new Tim role's auth Group (roles.GROUP_NAMES)."""
    apps.get_model("auth", "Group").objects.get_or_create(name="Tim Pemeriksaan Rusak/Tidak Layak")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0066_draft_perbaikan"),
    ]

    operations = [
        migrations.RunPython(buat_group, migrations.RunPython.noop),
    ]
