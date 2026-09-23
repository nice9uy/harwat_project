from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from django_bolt import BoltAPI
from django_bolt.auth import IsAuthenticated, JWTAuthentication
from django_bolt.exceptions import HTTPException
from django_bolt.serializers import Serializer, field
from django_bolt.views import CreateMixin, DestroyMixin, ListMixin, RetrieveMixin, UpdateMixin, ViewSet

from .models import Vehicle
from .services import get_fleet_summary

api = BoltAPI()

access_auth = JWTAuthentication(secret=settings.SECRET_KEY)


class VehicleWriteSerializer(Serializer):
    nopol: str
    jenis: str
    merek: str
    tahun: int
    status: str
    odometer_km: int
    penanggung_jawab: str


class VehicleSerializer(VehicleWriteSerializer):
    id: int = field(read_only=True)


class FleetSummaryResponse(Serializer):
    total: int
    ready: int
    in_repair: int
    due_soon: int


async def _save_vehicle(obj):
    # Django's save() only enforces DB-level constraints (uniqueness, CHECKs).
    # It never runs `choices=` (or other) field validation - that only happens
    # via full_clean(), which the HTML form calls implicitly through
    # form.is_valid(). Call it explicitly here so the API rejects the same
    # invalid input the form would. Django (as of this version) has no async
    # afull_clean(), so run the sync method off-thread via sync_to_async.
    #
    # validate_unique=False: skip nopol's uniqueness check here so a
    # duplicate nopol still falls through to asave() below and is reported
    # as 409 via the IntegrityError branch (the existing, more specific
    # contract), rather than as a generic 422 from this branch.
    try:
        await sync_to_async(obj.full_clean)(validate_unique=False)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message_dict)
    try:
        await obj.asave()
    except IntegrityError as exc:
        if "nopol" in str(exc):
            raise HTTPException(status_code=409, detail="A vehicle with this nopol already exists")
        raise HTTPException(status_code=422, detail="Vehicle violates a database constraint")


@api.viewset("/api/vehicles")
class VehicleViewSet(ListMixin, RetrieveMixin, CreateMixin, UpdateMixin, DestroyMixin, ViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    create_serializer_class = VehicleWriteSerializer
    auth = [access_auth]
    guards = [IsAuthenticated()]

    async def perform_create(self, obj):
        await _save_vehicle(obj)

    async def perform_update(self, obj):
        await _save_vehicle(obj)


@api.get("/api/fleet/summary", auth=[access_auth], guards=[IsAuthenticated()])
async def fleet_summary(request) -> FleetSummaryResponse:
    return await sync_to_async(get_fleet_summary)()
