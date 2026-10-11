"""Status menu. For the Tim roles: the work they have started and not saved
yet, and cancelling it. For the admins: that of the Tim members under them
(a superuser: of every Tim member)."""
import secrets
import string

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from . import roles
from .models import Anggota, DraftPemeriksaan, DraftPerbaikan, Laporan, PekerjaanAktif

_SESSION_CAPTCHA = "batal_pekerjaan_captcha"


def dicatat(user):
    """Whether the user's unsaved work is kept (inspection drafts, work under
    way) and reopened. Not for a superuser, who opens the forms to look at
    them rather than to do the work."""
    return not user.is_superuser


def mulai(user, jenis, vehicle=None, keterangan=""):
    """Note that a Tim member started a repair or an addition."""
    if roles.keanggotaan_kode(user) in roles.TIM:
        PekerjaanAktif.objects.update_or_create(
            user=user, jenis=jenis, vehicle=vehicle, defaults={"keterangan": keterangan},
        )


def selesai(user, jenis, vehicle=None):
    """The work was saved: it is no longer in progress."""
    PekerjaanAktif.objects.filter(user=user, jenis=jenis, vehicle=vehicle).delete()


def pekerjaan(user):
    """What the user is working on, newest first: [{jenis, vehicle, keterangan, waktu}]."""
    daftar = [
        {"jenis": "Pemeriksaan", "vehicle": d.vehicle, "keterangan": "", "waktu": d.diperbarui_pada}
        for d in DraftPemeriksaan.objects.filter(pemeriksa=user).select_related("vehicle")
    ] + [
        {"jenis": p.get_jenis_display(), "vehicle": p.vehicle, "keterangan": p.keterangan, "waktu": p.dimulai_pada}
        for p in PekerjaanAktif.objects.filter(user=user).select_related("vehicle")
    ]
    return sorted(daftar, key=lambda p: p["waktu"], reverse=True)


def status_tim(admin):
    """Every Tim member under ``admin`` (dashboard.cakupan), by Ketua Tim then
    username, each with the work they have under way (empty: Tidak Aktif)."""
    from .dashboard import cakupan

    users = cakupan(admin)
    nodes = list(Anggota.get_tree().select_related("user"))
    ketua = {n.path: n.user for n in nodes if n.depth == 1}
    anggota = [n for n in nodes if n.depth == 2 and (users is None or n.user_id in users)]
    ids = [n.user_id for n in anggota]
    kerja = {}
    for d in DraftPemeriksaan.objects.filter(pemeriksa__in=ids).select_related("vehicle"):
        kerja.setdefault(d.pemeriksa_id, []).append(
            {"jenis": "Pemeriksaan", "vehicle": d.vehicle, "keterangan": "", "waktu": d.diperbarui_pada}
        )
    for p in PekerjaanAktif.objects.filter(user__in=ids).select_related("vehicle"):
        kerja.setdefault(p.user_id, []).append(
            {"jenis": p.get_jenis_display(), "vehicle": p.vehicle, "keterangan": p.keterangan, "waktu": p.dimulai_pada}
        )
    nama = dict(Laporan.objects.filter(akun__in=ids).order_by("dibuat_pada").values_list("akun_id", "nama"))
    label = {n.user_id: roles.keanggotaan_label(n.user) for n in anggota}
    baris = [
        {
            "user": n.user, "nama": nama.get(n.user_id, ""), "keanggotaan": label[n.user_id],
            "ketua": ketua[n.path[:Anggota.steplen]],
            "pekerjaan": sorted(kerja.get(n.user_id, []), key=lambda p: p["waktu"], reverse=True),
        }
        for n in anggota
    ]
    baris.sort(key=lambda b: (b["ketua"].username, b["user"].username))
    return baris


@login_required
def status_view(request):
    if request.user.is_superuser or roles.keanggotaan_kode(request.user) in roles.ADMIN:
        baris = status_tim(request.user)
        return render(request, "accounts/status_tim.html", {
            "baris": baris, "jumlah_aktif": sum(1 for b in baris if b["pekerjaan"]),
        })
    return render(request, "accounts/status.html", {"pekerjaan": pekerjaan(request.user)})


@login_required
def status_batal(request):
    """GET: confirmation with a captcha for the Status modal. POST: drop the
    user's unsaved work (inspection drafts included), so their status is
    Tidak Aktif."""
    if request.method == "POST":
        kode = request.session.pop(_SESSION_CAPTCHA, None)
        if not kode or request.POST.get("captcha", "").strip() != kode:
            messages.error(request, "Kode verifikasi salah.")
            return redirect("accounts:status")
        with transaction.atomic():
            DraftPemeriksaan.objects.filter(pemeriksa=request.user).delete()
            PekerjaanAktif.objects.filter(user=request.user).delete()
            DraftPerbaikan.objects.filter(teknisi=request.user).delete()
        messages.success(request, "Pekerjaan dibatalkan. Status Anda sekarang tidak aktif.")
        return redirect("accounts:status")
    kode = "".join(secrets.choice(string.digits) for _ in range(6))
    request.session[_SESSION_CAPTCHA] = kode
    return render(request, "accounts/_status_batal_confirm.html", {
        "captcha_kode": kode, "pekerjaan": pekerjaan(request.user),
    })


def lanjut_pemeriksaan(user):
    """No. Registrasi of the inspection the user left unsaved (their latest
    draft), which Form Pemeriksaan reopens; "" when there is none."""
    if not dicatat(user):
        return ""
    draft = DraftPemeriksaan.objects.filter(pemeriksa=user).select_related("vehicle").order_by("-diperbarui_pada").first()
    return draft.vehicle.nopol if draft else ""


def lanjut_perbaikan(user):
    """No. Registrasi of the repair the user left unsaved, which Form
    Perbaikan reopens; "" when there is none."""
    if not dicatat(user):
        return ""
    kerja = (
        PekerjaanAktif.objects.filter(user=user, jenis=PekerjaanAktif.Jenis.PERBAIKAN, vehicle__isnull=False)
        .select_related("vehicle").order_by("-dimulai_pada").first()
    )
    return kerja.vehicle.nopol if kerja else ""


def lanjut_penambahan(user):
    """roles.FORM_TAMBAH key of the vehicle form the user left unsaved, which
    Form Tambah reopens; "" when there is none."""
    if not dicatat(user):
        return ""
    kerja = PekerjaanAktif.objects.filter(user=user, jenis=PekerjaanAktif.Jenis.PENAMBAHAN).first()
    kode_per_label = {label: kode for kode, label in roles.FORM_TAMBAH}
    return kode_per_label.get(kerja.keterangan, "") if kerja else ""
