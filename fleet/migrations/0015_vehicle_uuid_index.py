import uuid

from django.db import migrations, models


def isi_uuid(apps, schema_editor):
    Vehicle = apps.get_model("fleet", "Vehicle")
    for v in Vehicle.objects.only("pk"):
        Vehicle.objects.filter(pk=v.pk).update(uuid=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0014_vehicle_penambah"),
    ]

    operations = [
        # Added nullable, filled one row at a time, then made unique: a plain
        # AddField would give every existing row the same default UUID.
        migrations.AddField(
            model_name="vehicle",
            name="uuid",
            field=models.UUIDField(null=True, editable=False),
        ),
        migrations.RunPython(isi_uuid, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="vehicle",
            name="uuid",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
        migrations.AddIndex(
            model_name="vehicle",
            index=models.Index(fields=["group_kendaraan", "nopol"], name="vehicle_group_nopol_idx"),
        ),
    ]
