from django.db.models import Count

from .models import Vehicle


def get_fleet_summary() -> dict:
    status_counts = dict(Vehicle.objects.values_list("status").annotate(count=Count("id")))
    return {
        "total": sum(status_counts.values()),
        "ready": status_counts.get(Vehicle.Status.SIAP_PAKAI, 0),
        "in_repair": status_counts.get(Vehicle.Status.DALAM_PERBAIKAN, 0),
        "due_soon": status_counts.get(Vehicle.Status.PERLU_SERVIS, 0),
    }
