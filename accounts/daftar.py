"""Daftar sebagai Ketua Tim, from the login page.

Two modals: pick a matra, then fill in the account and the biodata (Info
Profil). The account is made switched off; an Admin of that matra (or a
superuser) switches it on under Aktivasi Ketua Tim (accounts.aktivasi).
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from fleet.images import compress_photo

from . import roles
from .forms import BiodataForm, DaftarKetuaForm, simpan_matra, simpan_satuan, terapkan_keanggotaan
from .models import Satuan, VpnPeer

# Sign-ups still waiting for activation at most: past that the form is closed
# until an Admin works through them, so nobody can flood the user table.
BATAS_MENUNGGU = 50


def menunggu_aktivasi():
    """Ketua Tim who signed up and were never switched on (never logged in)."""
    return User.objects.filter(
        groups__name=roles.GROUP_NAMES[roles.KETUA_TIM], is_active=False, last_login__isnull=True,
    )


def _forms(matra, data=None, files=None):
    akun = DaftarKetuaForm(data, prefix="daftar")
    biodata = BiodataForm(data, files, prefix="daftar")
    biodata.fields["foto"].required = True
    # Units of the matra picked in the first modal.
    biodata.fields["satuan"].queryset = Satuan.objects.filter(matra=matra).order_by("nama")
    return akun, biodata


@require_http_methods(["GET"])
def daftar_matra(request):
    return render(request, "accounts/_daftar_matra.html", {"matra_pilihan": roles.MATRA})


@require_http_methods(["GET", "POST"])
def daftar_form(request):
    matra = request.GET.get("matra", "")
    if matra not in dict(roles.MATRA):
        return daftar_matra(request)
    penuh = menunggu_aktivasi().count() >= BATAS_MENUNGGU
    if request.method == "POST" and not penuh:
        akun, biodata = _forms(matra, request.POST, request.FILES)
        if akun.is_valid() and biodata.is_valid():
            with transaction.atomic():
                user = User(username=akun.cleaned_data["username"], is_active=False)
                user.set_password(roles.DEFAULT_PASSWORD)
                user.save()
                terapkan_keanggotaan(user, roles.KETUA_TIM)
                simpan_matra(user, roles.KETUA_TIM, matra)
                simpan_satuan(user, biodata.cleaned_data["satuan"])
                laporan = biodata.save(commit=False)
                laporan.akun = user
                laporan.foto = compress_photo(request.FILES["daftar-foto"])
                laporan.save()
                from .vpn_utils import generate_keypair
                priv, pub = generate_keypair()
                VpnPeer.objects.create(user=user, peer_name=user.username, private_key=priv, public_key=pub)
            return render(request, "accounts/_daftar_selesai.html", {
                "username": user.username, "matra_label": dict(roles.MATRA)[matra],
            })
    else:
        akun, biodata = _forms(matra)
    return render(request, "accounts/_daftar_form.html", {
        "akun": akun, "form": biodata, "matra": matra, "matra_label": dict(roles.MATRA)[matra], "penuh": penuh, "kata_sandi_awal": roles.DEFAULT_PASSWORD,
    })
