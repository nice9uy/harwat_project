from django.db import migrations


def split_admin(apps, schema_editor):
    """The old Admin role becomes Admin Pusat; Admin Cabang is new."""
    Group = apps.get_model("auth", "Group")
    if not Group.objects.filter(name="Admin Pusat").exists():
        Group.objects.filter(name="Admin").update(name="Admin Pusat")
    Group.objects.get_or_create(name="Admin Pusat")
    Group.objects.get_or_create(name="Admin Cabang")


def merge_admin(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    pusat = Group.objects.get(name="Admin Pusat")
    for cabang in Group.objects.filter(name="Admin Cabang"):
        pusat.user_set.add(*cabang.user_set.all())
        cabang.delete()
    pusat.name = "Admin"
    pusat.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0029_uuid_publik"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(split_admin, merge_admin),
    ]
