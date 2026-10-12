"""Per-golongan wiring of the inspection and repair flows.

Each vehicle group has its own paper form, so its own inspection, item
and repair models; views look the group's entry up here instead of
hard-coding Golongan B.
"""
from dataclasses import dataclass

from fleet.models import Vehicle

from . import pemeriksaan as checklist
from .forms import (
    PemeriksaanBermotorForm,
    PemeriksaanDieselForm,
    PemeriksaanGolonganBForm,
    PemeriksaanJeepDieselForm,
    PemeriksaanRansusForm,
    PemeriksaanRantisForm,
)
from .models import (
    PemeriksaanBermotor,
    PemeriksaanBermotorItem,
    PemeriksaanDiesel,
    PemeriksaanDieselItem,
    PemeriksaanJeepDiesel,
    PemeriksaanRansus,
    PemeriksaanRantis,
    PemeriksaanJeepDieselItem,
    PemeriksaanRansusItem,
    PemeriksaanRantisItem,
    PemeriksaanGolonganB,
    PemeriksaanGolonganBItem,
    PerbaikanBermotor,
    PerbaikanDiesel,
    PerbaikanJeepDiesel,
    PerbaikanRansus,
    PerbaikanRantis,
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
    # Kondisi codes that need no repair: Baik, and Ada (the part is present).
    baik: tuple = ("B", "ADA")
    pakai_satuan: bool = False  # Sat / Jumlah Riil / Jumlah Nyata columns (diesel)
    # Chapters > systems > parts of the diesel-style checklists (their template).
    bab: tuple = ()


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
        pakai_satuan=True,
        bab=tuple(checklist.DIESEL_BAB),
    ),
    Vehicle.GroupKendaraan.JEEP_DIESEL: Golongan(
        form=PemeriksaanJeepDieselForm,
        pemeriksaan_model=PemeriksaanJeepDiesel,
        item_model=PemeriksaanJeepDieselItem,
        perbaikan_model=PerbaikanJeepDiesel,
        relasi="pemeriksaan_jeep_diesel",
        kondisi=checklist.KONDISI_JEEP_DIESEL,
        pakai_jumlah=False,
        template="accounts/_pemeriksaan_diesel.html",
        pakai_satuan=True,
        bab=tuple(checklist.JEEP_DIESEL_BAB),
    ),
    Vehicle.GroupKendaraan.RANTIS: Golongan(
        form=PemeriksaanRantisForm,
        pemeriksaan_model=PemeriksaanRantis,
        item_model=PemeriksaanRantisItem,
        perbaikan_model=PerbaikanRantis,
        relasi="pemeriksaan_rantis",
        kondisi=checklist.KONDISI_RANTIS,
        pakai_jumlah=False,
        template="accounts/_pemeriksaan_diesel.html",
        pakai_satuan=True,
        bab=tuple(checklist.RANTIS_BAB),
    ),
    Vehicle.GroupKendaraan.RANSUS: Golongan(
        form=PemeriksaanRansusForm,
        pemeriksaan_model=PemeriksaanRansus,
        item_model=PemeriksaanRansusItem,
        perbaikan_model=PerbaikanRansus,
        relasi="pemeriksaan_ransus",
        kondisi=checklist.KONDISI_RANSUS,
        pakai_jumlah=False,
        template="accounts/_pemeriksaan_diesel.html",
        pakai_satuan=True,
        bab=tuple(checklist.RANSUS_BAB),
    ),
}


def for_vehicle(vehicle):
    return GOLONGAN.get(vehicle.group_kendaraan) if vehicle is not None else None


# The inspector's Kesimpulan is the vehicle's status on the dashboard cards.
STATUS_KESIMPULAN = {
    "siap_pakai": Vehicle.Status.SIAP_PAKAI,
    "perlu_perbaikan": Vehicle.Status.PERLU_SERVIS,  # card "Rusak Ringan"
    "tidak_layak_pakai": Vehicle.Status.DALAM_PERBAIKAN,  # card "Rusak Berat"
}


def status_kendaraan(vehicle):
    """The vehicle's status from its latest inspection: what its Kesimpulan
    says (Siap Pakai -> Siap, Perlu Perbaikan -> Rusak Ringan, Tidak Layak
    Pakai -> Rusak Berat), with two corrections from the parts:

    * parts still not Baik under a Siap Pakai conclusion make it Rusak Ringan;
    * once every part that wasn't Baik has been repaired to Baik, it is Sudah
      Diperbaiki (until its next inspection).

    Siap when never inspected. A vehicle declared Rusak / Tidak Layak Pakai
    (models.KendaraanRusak) is Rusak Berat, until an inspection made after
    the declaration: the newest of the two decides.
    """
    cfg = for_vehicle(vehicle)
    terakhir = getattr(vehicle, cfg.relasi).order_by("-dibuat_pada", "-id").first() if cfg else None
    dinyatakan = vehicle.rusak.order_by("-dibuat_pada", "-id").first()
    if dinyatakan is not None and (terakhir is None or terakhir.dibuat_pada <= dinyatakan.dibuat_pada):
        return Vehicle.Status.DALAM_PERBAIKAN
    if terakhir is None:
        return Vehicle.Status.SIAP_PAKAI
    awal = dict(terakhir.items.values_list("pk", "kondisi"))
    kini = dict(awal)
    # Oldest first, so each part ends on its latest repair.
    for item_id, kode in (
        cfg.perbaikan_model.objects.filter(item__pemeriksaan=terakhir)
        .order_by("dibuat_pada", "id").values_list("item_id", "kondisi")
    ):
        kini[item_id] = kode
    pernah_rusak = any(kode not in cfg.baik for kode in awal.values())
    masih_rusak = any(kode not in cfg.baik for kode in kini.values())
    if pernah_rusak and not masih_rusak:
        return Vehicle.Status.SUDAH_DIPERBAIKI
    status = STATUS_KESIMPULAN.get(terakhir.kesimpulan, Vehicle.Status.SIAP_PAKAI)
    if masih_rusak and status == Vehicle.Status.SIAP_PAKAI:
        return Vehicle.Status.PERLU_SERVIS
    return status


def perbarui_status(vehicle):
    """Store status_kendaraan(); called whenever an inspection or a repair is saved."""
    status = status_kendaraan(vehicle)
    if vehicle.status != status:
        vehicle.status = status
        vehicle.save(update_fields=["status"])
    return status
