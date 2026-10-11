"""Pimpinan Tim: a Pimpinan over chosen teams. They pick the Ketua Tim under
them, and see those teams where a Pimpinan sees everyone."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from . import roles
from .models import Anggota, BawahanPimpinan, Laporan


def ketua_bawahan(user):
    """pks of the Ketua Tim nodes ``user`` (a Pimpinan Tim) has picked."""
    return set(BawahanPimpinan.objects.filter(pimpinan=user).values_list("ketua_id", flat=True))


def tim_terlihat(user):
    """pks of the Ketua Tim nodes a Pimpinan Tim is limited to, or None for
    anyone else (no limit from this role)."""
    return ketua_bawahan(user) if roles.keanggotaan_kode(user) == roles.PIMPINAN_TIM else None


@login_required
def bawahan_view(request, uid):
    """Modal to pick a Pimpinan Tim's Ketua Tim: for that Pimpinan Tim
    themselves and for a superuser. GET: every Ketua Tim, ticked when picked.
    POST: keep exactly the ticked ones."""
    pimpinan = get_object_or_404(User, publik__uuid=uid)
    if roles.keanggotaan_kode(pimpinan) != roles.PIMPINAN_TIM or not (
        request.user.is_superuser or request.user.pk == pimpinan.pk
    ):
        return HttpResponse(status=403)
    ketua = list(Anggota.get_root_nodes().select_related("user").order_by("user__username"))
    sendiri = request.user.pk == pimpinan.pk
    if request.method == "POST":
        dipilih = {str(n.uuid): n for n in ketua}
        baru = [dipilih[u] for u in request.POST.getlist("ketua") if u in dipilih]
        with transaction.atomic():
            BawahanPimpinan.objects.filter(pimpinan=pimpinan).exclude(ketua__in=baru).delete()
            ada = ketua_bawahan(pimpinan)
            BawahanPimpinan.objects.bulk_create(
                [BawahanPimpinan(pimpinan=pimpinan, ketua=n) for n in baru if n.pk not in ada]
            )
        messages.success(request, f"Ketua Tim bawahan {pimpinan.username}: {len(baru)} dipilih.")
        return redirect("accounts:anggota_tim" if sendiri else "accounts:pengaturan")
    punya = ketua_bawahan(pimpinan)
    nama = dict(Laporan.objects.filter(akun__in=[n.user_id for n in ketua]).order_by("dibuat_pada").values_list("akun_id", "nama"))
    return render(request, "accounts/_pimpinan_tim_bawahan.html", {
        "pimpinan": pimpinan, "sendiri": sendiri,
        "ketua": [
            {"uuid": n.uuid, "username": n.user.username, "nama": nama.get(n.user_id, ""),
             "anggota": n.get_children_count(), "dipilih": n.pk in punya}
            for n in ketua
        ],
    })
