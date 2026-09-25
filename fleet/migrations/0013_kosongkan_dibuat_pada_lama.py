from datetime import timedelta

from django.db import migrations


def kosongkan(apps, schema_editor):
    """0012 filled dibuat_pada of existing vehicles with the migration time.

    That time is not when they were added, so clear it for vehicles stamped
    around when 0012 was applied.
    """
    from django.db.migrations.recorder import MigrationRecorder

    record = MigrationRecorder(schema_editor.connection).migration_qs.filter(
        app="fleet", name="0012_vehicle_dibuat_pada"
    ).first()
    if record is None:
        return
    Vehicle = apps.get_model("fleet", "Vehicle")
    Vehicle.objects.filter(
        dibuat_pada__gte=record.applied - timedelta(minutes=5),
        dibuat_pada__lte=record.applied + timedelta(seconds=5),
    ).update(dibuat_pada=None)


class Migration(migrations.Migration):

    dependencies = [
        ("fleet", "0012_vehicle_dibuat_pada"),
    ]

    operations = [
        migrations.RunPython(kosongkan, migrations.RunPython.noop),
    ]
