import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def satukan(apps, schema_editor):
    """One Admin role instead of Admin Pusat > Admin Cabang.

    Admin Pusat becomes Admin. A Ketua Tim an Admin Cabang owned goes to
    that Admin Cabang's Admin Pusat. The Admin Cabang accounts lose the role
    and are switched off (not deleted: their biodata and work stay), to be
    given another role or removed from Pengaturan.
    """
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    AdminCabang = apps.get_model("accounts", "AdminCabang")
    Anggota = apps.get_model("accounts", "Anggota")

    pusat_dari = dict(AdminCabang.objects.values_list("user_id", "admin_pusat_id"))
    for node in Anggota.objects.exclude(admin_cabang=None):
        # None when the owner was an Admin Cabang no Admin Pusat was above.
        node.admin_cabang_id = pusat_dari.get(node.admin_cabang_id)
        node.save(update_fields=["admin_cabang"])

    cabang = Group.objects.filter(name="Admin Cabang").first()
    if cabang is not None:
        for user in User.objects.filter(groups=cabang):
            user.groups.remove(cabang)
            user.is_active = False
            user.is_staff = False
            user.save(update_fields=["is_active", "is_staff"])
        cabang.delete()
    AdminCabang.objects.all().delete()

    if Group.objects.filter(name="Admin").exists():
        # Both names there (not expected): fold Admin Pusat into Admin.
        admin = Group.objects.get(name="Admin")
        for pusat in Group.objects.filter(name="Admin Pusat"):
            for user in User.objects.filter(groups=pusat):
                user.groups.add(admin)
            pusat.delete()
    else:
        Group.objects.filter(name="Admin Pusat").update(name="Admin")
    Group.objects.get_or_create(name="Admin")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0057_km_jadwal_rantis"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(satukan, migrations.RunPython.noop),
        migrations.DeleteModel(name="AdminCabang"),
        migrations.RenameField(model_name="anggota", old_name="admin_cabang", new_name="admin"),
        migrations.AlterField(
            model_name="anggota",
            name="admin",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="ketua_tim_list", to=settings.AUTH_USER_MODEL, verbose_name="Admin",
            ),
        ),
    ]
