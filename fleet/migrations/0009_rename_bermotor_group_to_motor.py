from django.db import migrations, models


def rename_group(apps, old, new):
    apps.get_model("fleet", "Vehicle").objects.filter(group_kendaraan=old).update(group_kendaraan=new)


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0008_kendaraan_bermotor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vehicle",
            name="group_kendaraan",
            field=models.CharField(
                choices=[("B", "Golongan B"), ("motor", "Motor")],
                db_index=True,
                default="B",
                max_length=10,
                verbose_name="Group Kendaraan",
            ),
        ),
        migrations.RunPython(
            lambda apps, schema_editor: rename_group(apps, "bermotor", "motor"),
            lambda apps, schema_editor: rename_group(apps, "motor", "bermotor"),
        ),
    ]
