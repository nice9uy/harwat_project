from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0024_add_draft_pemeriksaan'),
    ]

    operations = [
        migrations.AddField(
            model_name='vpnpeer',
            name='private_key',
            field=models.TextField(blank=True, verbose_name='Private Key'),
        ),
        migrations.AddField(
            model_name='vpnpeer',
            name='public_key',
            field=models.TextField(blank=True, verbose_name='Public Key'),
        ),
        migrations.AddField(
            model_name='vpnpeer',
            name='client_ip',
            field=models.CharField(blank=True, max_length=50, verbose_name='IP Client (CIDR)'),
        ),
        migrations.AddField(
            model_name='vpnpeer',
            name='preshared_key',
            field=models.TextField(blank=True, verbose_name='Preshared Key'),
        ),
    ]
