from django.db import migrations


def create_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.get_or_create(name="Ketua Tim")


def delete_group(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name="Ketua Tim").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_anggota_tree"),
    ]

    operations = [
        migrations.RunPython(create_group, delete_group),
    ]
