from django import template

register = template.Library()


@register.filter
def rupiah(nilai):
    """1250000 -> "Rp 1.250.000"; empty stays "-"."""
    if nilai in (None, ""):
        return "-"
    return "Rp " + f"{int(nilai):,}".replace(",", ".")
