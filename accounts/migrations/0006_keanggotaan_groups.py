from django.db import migrations

GROUP_NAMES = [
    "Admin",
    "Pimpinan",
    "Petugas Pemeriksaan",
    "Petugas Penambahan Data",
    "Petugas Perbaikan",
]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUP_NAMES:
        Group.objects.get_or_create(name=name)


def delete_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=GROUP_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_perbaikan_golongan_b"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, delete_groups),
    ]
