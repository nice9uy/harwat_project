from django.conf import settings
from django.db import IntegrityError

from django_bolt import BoltAPI
from django_bolt.auth import IsAuthenticated, JWTAuthentication
from django_bolt.exceptions import HTTPException
from django_bolt.serializers import Serializer, field
from django_bolt.views import ModelViewSet

from .models import Vehicle

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


@api.viewset("/api/vehicles")
class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    create_serializer_class = VehicleWriteSerializer
    auth = [access_auth]
    guards = [IsAuthenticated()]

    async def perform_create(self, obj):
        try:
            await obj.asave()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A vehicle with this nopol already exists")

    async def perform_update(self, obj):
        try:
            await obj.asave()
        except IntegrityError:
            raise HTTPException(status_code=409, detail="A vehicle with this nopol already exists")
