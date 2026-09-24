from django.db import migrations


class Migration(migrations.Migration):
    """Kendaraan Bermotor is now called Motor; rename the models (and their tables)."""

    dependencies = [
        ("accounts", "0010_bermotor_tanpa_jumlah"),
        ("fleet", "0008_kendaraan_bermotor"),
    ]

    operations = [
        migrations.RenameModel("PemeriksaanBermotor", "PemeriksaanMotor"),
        migrations.RenameModel("PemeriksaanBermotorItem", "PemeriksaanMotorItem"),
        migrations.RenameModel("PerbaikanBermotor", "PerbaikanMotor"),
    ]
