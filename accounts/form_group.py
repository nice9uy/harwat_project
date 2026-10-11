"""Form Group: which Form Tambah forms each Ketua Tim's team, and each Tim
Penambahan Data member in it, may open."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from . import roles
from .models import AksesFormTambah, Anggota

_GROUP_PENAMBAH = roles.GROUP_NAMES["tim_penambahan_data"]
SEMUA = [kode for kode, _ in roles.FORM_TAMBAH]
LABEL = dict(roles.FORM_TAMBAH)


def _superuser(request):
    if not request.user.is_superuser:
        raise Http404


def _penambah(nodes):
    """Of these member nodes, the Tim Penambahan Data ones, by username."""
    pks = set(
        Anggota.objects.filter(pk__in=[n.pk for n in nodes], user__groups__name=_GROUP_PENAMBAH)
        .values_list("pk", flat=True)
    )
    return sorted((n for n in nodes if n.pk in pks), key=lambda n: n.user.username)


def _form(akses, user_id, ketua_id=None):
    """Forms of a user: their own setting, else their Ketua Tim's, else all."""
    form = akses.get(user_id)
    if form is None and ketua_id is not None:
        form = akses.get(ketua_id)
    return [kode for kode in SEMUA if form is None or kode in form]


def _target(uid):
    """(user, node, members) of a Form Group row: a Ketua Tim with their Tim
    Penambahan Data members, or one such member (members: [])."""
    user = get_object_or_404(User, publik__uuid=uid)
    node = get_object_or_404(Anggota, user=user)
    if node.is_root():
        return user, node, _penambah(list(node.get_children().select_related("user")))
    if not user.groups.filter(name=_GROUP_PENAMBAH).exists():
        raise Http404
    return user, node, []


def _form_user(user, node):
    akses = dict(AksesFormTambah.objects.values_list("user_id", "form"))
    return _form(akses, user.pk, None if node.is_root() else node.get_parent().user_id)


def _ubah(user, node, anggota, kode_list, tambah):
    """Add or remove forms on a row. On a Ketua Tim row it applies to the
    team: the setting kept on the Ketua Tim (new members start from it) and
    every member."""
    with transaction.atomic():
        for u, n in [(user, node), *((a.user, a) for a in anggota)]:
            form = set(_form_user(u, n))
            form = form | set(kode_list) if tambah else form - set(kode_list)
            AksesFormTambah.objects.update_or_create(
                user=u, defaults={"form": [kode for kode in SEMUA if kode in form]},
            )


def _kembali():
    response = HttpResponse(status=204)
    response["HX-Redirect"] = reverse("accounts:form_group")
    return response


@login_required
def form_group_view(request):
    """Superuser only. Every Ketua Tim with their Tim Penambahan Data members
    under them: the forms each may open, and Tambah Form / Hapus Form."""
    _superuser(request)
    nodes = list(Anggota.get_tree().select_related("user", "user__publik"))
    anggota = _penambah([n for n in nodes if n.depth == 2])
    akses = dict(AksesFormTambah.objects.values_list("user_id", "form"))
    baris = []
    for ketua in sorted((n for n in nodes if n.depth == 1), key=lambda n: n.user.username):
        tim = [n for n in anggota if n.path.startswith(ketua.path)]
        baris.append({
            "user": ketua.user, "ketua": ketua.user, "jumlah": len(tim), "kedalaman": 0,
            "form": [(kode, LABEL[kode]) for kode in _form(akses, ketua.user_id)],
        })
        for node in tim:
            baris.append({
                "user": node.user, "ketua": ketua.user, "kedalaman": 1,
                "form": [(kode, LABEL[kode]) for kode in _form(akses, node.user_id, ketua.user_id)],
            })
    return render(request, "accounts/form_group.html", {"baris": baris})


@login_required
def form_group_lihat(request, uid):
    """Modal: the forms a row may open."""
    _superuser(request)
    user, node, anggota = _target(uid)
    return render(request, "accounts/_form_group_lihat.html", {
        "akun": user, "ketua": node.is_root(), "jumlah": len(anggota),
        "form": [(kode, LABEL[kode]) for kode in _form_user(user, node)],
    })


@login_required
def form_group_tambah(request, uid):
    """Modal listing the forms a row doesn't have yet, laid out like Form
    Tambah (Kendaraan / Non Kendaraan); POST adds the ticked ones."""
    _superuser(request)
    user, node, anggota = _target(uid)
    if request.method == "POST":
        dipilih = [kode for kode in request.POST.getlist("kode") if kode in SEMUA]
        if dipilih:
            _ubah(user, node, anggota, dipilih, tambah=True)
            messages.success(
                request, f"Form {', '.join(LABEL[k] for k in SEMUA if k in dipilih)} ditambahkan untuk {user.username}.",
            )
            return _kembali()
    punya = _form_user(user, node)
    kendaraan = [(kode, LABEL[kode], kode in punya) for kode in SEMUA if kode != "non_kendaraan"]
    return render(request, "accounts/_form_group_tambah.html", {
        "akun": user, "ketua": node.is_root(), "jumlah": len(anggota),
        "kendaraan": kendaraan, "punya_non_kendaraan": "non_kendaraan" in punya,
        "kosong": request.method == "POST", "lengkap": len(punya) == len(SEMUA),
    })


@login_required
def form_group_hapus(request, uid):
    """Modal listing a row's forms, each with a Hapus button; ?kode=<kode>
    asks to confirm that one; POST removes it."""
    _superuser(request)
    user, node, anggota = _target(uid)
    if request.method == "POST":
        kode = request.POST.get("kode")
        if kode in SEMUA:
            _ubah(user, node, anggota, [kode], tambah=False)
            messages.success(request, f"Form {LABEL[kode]} dihapus dari {user.username}.")
        return _kembali()
    punya = _form_user(user, node)
    kode = request.GET.get("kode")
    if kode in punya:
        return render(request, "accounts/_form_group_hapus_confirm.html", {
            "akun": user, "ketua": node.is_root(), "jumlah": len(anggota), "kode": kode, "label": LABEL[kode],
        })
    return render(request, "accounts/_form_group_hapus.html", {
        "akun": user, "ketua": node.is_root(), "jumlah": len(anggota),
        "form": [(kode, LABEL[kode]) for kode in _form_user(user, node)],
    })
