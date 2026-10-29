"""Usernames unique whatever their case, in the database too: a unique index
on LOWER(username) (SQLite and PostgreSQL alike), so two "ketua"/"Ketua"
accounts can't come in by any route, nor by two requests at once. Where such
pairs already exist the index is left out (and they are named), so a deploy
doesn't stop on it; the forms still refuse new ones."""
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower

INDEX = "auth_user_username_lower_uniq"


def buat(apps, schema_editor):
    User = apps.get_model("auth", "User")
    kembar = [
        b["nama"] for b in User.objects.annotate(nama=Lower("username")).values("nama")
        .annotate(n=Count("id")).filter(n__gt=1)
    ]
    if kembar:
        print(f"\n  Index {INDEX} tidak dibuat: nama pengguna kembar (beda huruf besar/kecil saja): {', '.join(kembar)}")
        return
    schema_editor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON auth_user (LOWER(username))")


def hapus(apps, schema_editor):
    schema_editor.execute(f"DROP INDEX IF EXISTS {INDEX}")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0072_gagal_login"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(buat, hapus)]
