"""Aktivasi Ketua Tim: switching Ketua Tim accounts on and off.

A superuser sees every Ketua Tim; an Admin only those of their own matra.
A switched-off account stays, with its team and data, but can't log in.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import dashboard, roles
from .models import Anggota, Laporan
from .roles import keanggotaan_label


def _matra_admin(user):
    """The one matra whose Ketua Tim ``user`` activates: "" for a superuser
    (any), None for a role that activates none."""
    if user.is_superuser:
        return ""
    if roles.keanggotaan_kode(user) != roles.ADMIN_ROLE:
        return None
    return getattr(getattr(user, "publik", None), "matra", "") or None


def _ketua_tim(matra):
    """Ketua Tim accounts with their matra (their own, else their Admin's),
    narrowed to ``matra`` when given."""
    semua = (
        User.objects.filter(groups__name=roles.GROUP_NAMES[roles.KETUA_TIM])
        .select_related("publik", "publik__satuan").order_by("username")
    )
    matra_per_akun = dashboard._matra_pengguna()
    hasil = []
    for akun in semua:
        akun.matra = matra_per_akun.get(akun.pk, "")
        if not matra or akun.matra == matra:
            hasil.append(akun)
    return hasil


def jumlah_menunggu(user):
    """How many sign-ups wait for ``user`` to activate them (the badge on the
    Aktivasi Ketua Tim menu): of their matra for an Admin, all for a superuser."""
    from .daftar import menunggu_aktivasi

    matra = _matra_admin(user)
    if matra is None:
        return 0
    ids = list(menunggu_aktivasi().values_list("pk", flat=True))
    if not matra or not ids:
        return len(ids)
    matra_per_akun = dashboard._matra_pengguna()
    return sum(1 for pk in ids if matra_per_akun.get(pk, "") == matra)


@login_required
def aktivasi_ketua_tim(request):
    matra_admin = _matra_admin(request.user)
    if matra_admin is None:
        return HttpResponse(status=403)
    # A superuser narrows the list to one matra (?matra=); an Admin has theirs.
    pilih = request.GET.get("matra", "")
    matra = matra_admin or (pilih if pilih in dict(roles.MATRA) else "")
    daftar = _ketua_tim(matra)
    biodata = dict(  # user pk -> name and unit of their newest biodata
        (akun_id, (nama, satuan))
        for akun_id, nama, satuan in Laporan.objects.filter(akun__in=[a.pk for a in daftar])
        .order_by("dibuat_pada").values_list("akun_id", "nama", "satuan__nama")
    )
    admin = dict(Anggota.objects.filter(depth=1, user__in=daftar).values_list("user_id", "admin__username"))
    label_matra = dict(roles.MATRA)
    for akun in daftar:
        nama, satuan = biodata.get(akun.pk, ("", ""))
        akun.nama_biodata = nama or akun.get_full_name()
        akun.satuan_label = akun.publik.satuan.nama if getattr(akun.publik, "satuan", None) else satuan or ""
        akun.matra_label = label_matra.get(akun.matra, "")
        akun.admin_label = admin.get(akun.pk) or ""
    # Sign-ups waiting for activation first.
    daftar.sort(key=lambda a: a.is_active or a.last_login is not None)
    return render(request, "accounts/aktivasi_ketua_tim.html", {
        "daftar": daftar,
        "pilih_matra": not matra_admin,
        "matra": matra,
        "matra_pilihan": roles.MATRA,
        "matra_label": label_matra.get(matra_admin, ""),
        "jumlah_aktif": sum(1 for a in daftar if a.is_active),
    })


@login_required
def aktivasi_ketua_tim_ubah(request, user_uid):
    """GET: confirmation. POST: switch the Ketua Tim on or off."""
    matra_admin = _matra_admin(request.user)
    target = get_object_or_404(User, publik__uuid=user_uid)
    if matra_admin is None or roles.keanggotaan_kode(target) != roles.KETUA_TIM:
        return HttpResponse(status=403)
    if matra_admin and dashboard._matra_pengguna().get(target.pk, "") != matra_admin:
        return HttpResponse(status=403)
    if request.method == "POST":
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        # A Ketua Tim who signed up themselves (accounts.daftar) has no Admin
        # yet: the Admin switching them on takes them under their wing.
        if target.is_active and not request.user.is_superuser:
            Anggota.objects.filter(user=target, depth=1, admin__isnull=True).update(admin=request.user)
        messages.success(request, f"Ketua Tim {target.username} {'diaktifkan' if target.is_active else 'dinonaktifkan'}.")
        tujuan = reverse("accounts:aktivasi_ketua_tim")
        if request.POST.get("matra") in dict(roles.MATRA):
            tujuan += f"?matra={request.POST['matra']}"
        return redirect(tujuan)
    return render(request, "accounts/_anggota_aktif_confirm.html", {
        "target": target, "keanggotaan": keanggotaan_label(target),
        "aksi_url": reverse("accounts:aktivasi_ketua_tim_ubah", args=[target.publik.uuid]),
        "matra": request.GET.get("matra", ""),
    })
