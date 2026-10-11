import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MODEL = [
    "pemeriksaangolonganb", "perbaikangolonganb", "pemeriksaanbermotor", "perbaikanbermotor",
    "pemeriksaandiesel", "perbaikandiesel", "anggota", "satuan",
]


def isi_uuid(apps, schema_editor):
    for nama in MODEL:
        Model = apps.get_model("accounts", nama)
        for pk in Model.objects.values_list("pk", flat=True):
            Model.objects.filter(pk=pk).update(uuid=uuid.uuid4())
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    AkunPublik = apps.get_model("accounts", "AkunPublik")
    AkunPublik.objects.bulk_create(
        [AkunPublik(user_id=pk, uuid=uuid.uuid4()) for pk in User.objects.values_list("pk", flat=True)]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0028_pemeriksaan_keterangan"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # Each uuid is added nullable, filled row by row, then made unique: a plain
    # AddField would give every existing row the same default UUID.
    operations = [
        *[
            migrations.AddField(model_name=nama, name="uuid", field=models.UUIDField(null=True, editable=False))
            for nama in MODEL
        ],
        migrations.CreateModel(
            name="AkunPublik",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE, related_name="publik", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"verbose_name": "UUID Akun", "verbose_name_plural": "UUID Akun"},
        ),
        migrations.RunPython(isi_uuid, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=nama, name="uuid",
                field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
            )
            for nama in MODEL
        ],
    ]
