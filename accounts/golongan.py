"""Per-golongan wiring of the inspection and repair flows.

Each vehicle group has its own paper form, so its own inspection, item
and repair models; views look the group's entry up here instead of
hard-coding Golongan B.
"""
from dataclasses import dataclass

from fleet.models import Vehicle

from . import pemeriksaan as checklist
from .forms import PemeriksaanMotorForm, PemeriksaanGolonganBForm
from .models import (
    PemeriksaanMotor,
    PemeriksaanMotorItem,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanMotor,
    PerbaikanGolonganB,
)


@dataclass(frozen=True)
class Golongan:
    form: type
    pemeriksaan_model: type
    item_model: type
    perbaikan_model: type
    relasi: str  # Vehicle related_name of the inspections
    kondisi: list
    pakai_jumlah: bool  # the paper form has a Jumlah column
    baik: str = "B"


GOLONGAN = {
    Vehicle.GroupKendaraan.GOLONGAN_B: Golongan(
        form=PemeriksaanGolonganBForm,
        pemeriksaan_model=PemeriksaanGolonganB,
        item_model=PemeriksaanGolonganBItem,
        perbaikan_model=PerbaikanGolonganB,
        relasi="pemeriksaan_golongan_b",
        kondisi=checklist.KONDISI,
        pakai_jumlah=True,
    ),
    Vehicle.GroupKendaraan.MOTOR: Golongan(
        form=PemeriksaanMotorForm,
        pemeriksaan_model=PemeriksaanMotor,
        item_model=PemeriksaanMotorItem,
        perbaikan_model=PerbaikanMotor,
        relasi="pemeriksaan_motor",
        kondisi=checklist.KONDISI_MOTOR,
        pakai_jumlah=False,
    ),
}


def for_vehicle(vehicle):
    return GOLONGAN.get(vehicle.group_kendaraan) if vehicle is not None else None
