import uuid

from django.db import migrations, models

MODEL = ["jadwal", "servis"]


def isi_uuid(apps, schema_editor):
    for nama in MODEL:
        Model = apps.get_model("fleet", nama)
        for pk in Model.objects.values_list("pk", flat=True):
            Model.objects.filter(pk=pk).update(uuid=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0015_vehicle_uuid_index"),
    ]

    # Nullable first, filled row by row, then unique (see 0015).
    operations = [
        *[
            migrations.AddField(model_name=nama, name="uuid", field=models.UUIDField(null=True, editable=False))
            for nama in MODEL
        ],
        migrations.RunPython(isi_uuid, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=nama, name="uuid",
                field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
            )
            for nama in MODEL
        ],
    ]
