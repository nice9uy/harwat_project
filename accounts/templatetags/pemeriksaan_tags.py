from django import template

from accounts.pemeriksaan import KONDISI_WARNA, KONDISI_WARNA_DIPILIH

register = template.Library()


@register.filter
def kondisi_warna(kode):
    """Badge background class for a kondisi code (B, RR, RB, HP, HG, TA)."""
    return KONDISI_WARNA.get(kode, "bg-slate-500")


@register.filter
def kondisi_warna_dipilih(kode):
    """Classes for a selected kondisi radio button."""
    return KONDISI_WARNA_DIPILIH.get(kode, "")
