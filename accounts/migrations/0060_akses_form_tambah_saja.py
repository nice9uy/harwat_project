from django.db import migrations, models


def buang_tanpa_form(apps, schema_editor):
    """Form Group is for Form Tambah only again: a row that only held a Form
    Pemeriksaan / Form Perbaikan setting (0059) has no Form Tambah list, and
    goes, leaving that user on their Ketua Tim's setting or on every form."""
    apps.get_model("accounts", "AksesFormTambah").objects.filter(form=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0059_akses_form_tiga_jenis"),
    ]

    operations = [
        migrations.RunPython(buang_tanpa_form, migrations.RunPython.noop),
        migrations.RemoveField(model_name="aksesformtambah", name="pemeriksaan"),
        migrations.RemoveField(model_name="aksesformtambah", name="perbaikan"),
        migrations.AlterField(model_name="aksesformtambah", name="form", field=models.JSONField(default=list)),
        migrations.AlterModelOptions(
            name="aksesformtambah",
            options={"verbose_name": "Akses Form Tambah", "verbose_name_plural": "Akses Form Tambah"},
        ),
    ]
