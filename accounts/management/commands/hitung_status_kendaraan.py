from django.core.management.base import BaseCommand

from accounts import golongan
from fleet.models import Vehicle


class Command(BaseCommand):
    help = (
        "Recompute every vehicle's status (Siap / Rusak Ringan / Rusak Berat) from its latest "
        "inspection and repairs. For data saved before the status followed them."
    )

    def handle(self, *args, **options):
        berubah = 0
        for vehicle in Vehicle.objects.all():
            lama = vehicle.status
            if golongan.perbarui_status(vehicle) != lama:
                berubah += 1
                self.stdout.write(f"{vehicle.nopol}: {lama} -> {vehicle.status}")
        self.stdout.write(self.style.SUCCESS(f"{berubah} kendaraan diperbarui."))
