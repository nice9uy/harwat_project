from django.db import migrations

RENAMES = {
    "Petugas Pemeriksaan": "Tim Pemeriksaan",
    "Petugas Penambahan Data": "Tim Penambahan Data",
    "Petugas Perbaikan": "Tim Perbaikan",
}


def rename(apps, mapping):
    # Renaming (not recreating) keeps existing users in their group.
    Group = apps.get_model("auth", "Group")
    for old, new in mapping.items():
        Group.objects.filter(name=old).update(name=new)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_keanggotaan_groups"),
    ]

    operations = [
        migrations.RunPython(
            lambda apps, schema_editor: rename(apps, RENAMES),
            lambda apps, schema_editor: rename(apps, {new: old for old, new in RENAMES.items()}),
        ),
    ]
