"""Per-golongan wiring of the inspection and repair flows.

Each vehicle group has its own paper form, so its own inspection, item
and repair models; views look the group's entry up here instead of
hard-coding Golongan B.
"""
from dataclasses import dataclass

from fleet.models import Vehicle

from . import pemeriksaan as checklist
from .forms import PemeriksaanBermotorForm, PemeriksaanDieselForm, PemeriksaanGolonganBForm
from .models import (
    PemeriksaanBermotor,
    PemeriksaanBermotorItem,
    PemeriksaanDiesel,
    PemeriksaanDieselItem,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanBermotor,
    PerbaikanDiesel,
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
    template: str  # checklist shown after the QR scan
    baik: tuple = ("B",)  # kondisi codes that need no repair
    pakai_satuan: bool = False  # Sat / Jumlah Riil / Jumlah Nyata columns (diesel)


GOLONGAN = {
    Vehicle.GroupKendaraan.GOLONGAN_B: Golongan(
        form=PemeriksaanGolonganBForm,
        pemeriksaan_model=PemeriksaanGolonganB,
        item_model=PemeriksaanGolonganBItem,
        perbaikan_model=PerbaikanGolonganB,
        relasi="pemeriksaan_golongan_b",
        kondisi=checklist.KONDISI,
        pakai_jumlah=True,
        template="accounts/_pemeriksaan_golongan_b.html",
    ),
    Vehicle.GroupKendaraan.KENDARAAN_BERMOTOR: Golongan(
        form=PemeriksaanBermotorForm,
        pemeriksaan_model=PemeriksaanBermotor,
        item_model=PemeriksaanBermotorItem,
        perbaikan_model=PerbaikanBermotor,
        relasi="pemeriksaan_bermotor",
        kondisi=checklist.KONDISI_BERMOTOR,
        pakai_jumlah=False,
        template="accounts/_pemeriksaan_bermotor.html",
    ),
    Vehicle.GroupKendaraan.KENDARAAN_DIESEL: Golongan(
        form=PemeriksaanDieselForm,
        pemeriksaan_model=PemeriksaanDiesel,
        item_model=PemeriksaanDieselItem,
        perbaikan_model=PerbaikanDiesel,
        relasi="pemeriksaan_diesel",
        kondisi=checklist.KONDISI_DIESEL,
        pakai_jumlah=False,
        template="accounts/_pemeriksaan_diesel.html",
        baik=("B", "ADA"),
        pakai_satuan=True,
    ),
}


def for_vehicle(vehicle):
    return GOLONGAN.get(vehicle.group_kendaraan) if vehicle is not None else None
