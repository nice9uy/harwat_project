"""Laporan Tim: each Ketua Tim's team with its activity (inspections, repairs,
vehicles added) in the chosen period and vehicle group.

Activity is tied to a team member through the account that submitted it
(Laporan.akun, Vehicle.ditambahkan_oleh), so work recorded before those
columns existed isn't counted.
"""
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode

from fleet.models import Vehicle

from .laporan import _filter, _golongan_dipilih, _keterangan_filter, _render, _rentang
from .models import Anggota
from .roles import keanggotaan_label

JENIS = ["pemeriksaan", "perbaikan", "penambahan"]
MAKS_AKTIVITAS = 100


def _tim():
    """[(ketua node, [member nodes])] sorted by username, each node with ``user``."""
    nodes = list(Anggota.get_tree().select_related("user"))
    tim = []
    for ketua in sorted((n for n in nodes if n.depth == 1), key=lambda n: n.user.username):
        anggota = sorted(
            (n for n in nodes if n.depth == 2 and n.path.startswith(ketua.path)), key=lambda n: n.user.username,
        )
        tim.append((ketua, anggota))
    return tim


def _jumlah_per_akun(f, user_ids):
    """{user id: {"pemeriksaan": n, "perbaikan": n, "penambahan": n}} in the filter's period and group."""
    jumlah = defaultdict(lambda: dict.fromkeys(JENIS, 0))
    for _, cfg in _golongan_dipilih(f):
        for model, akun, jenis in (
            (cfg.pemeriksaan_model, "pemeriksa__akun", "pemeriksaan"),
            (cfg.perbaikan_model, "teknisi__akun", "perbaikan"),
        ):
            qs = _rentang(model.objects.filter(**{f"{akun}__in": user_ids}), "dibuat_pada", f)
            for baris in qs.order_by().values(akun).annotate(n=Count("id")):
                jumlah[baris[akun]][jenis] += baris["n"]
    kendaraan = Vehicle.objects.filter(ditambahkan_oleh__in=user_ids)
    if f["golongan"]:
        kendaraan = kendaraan.filter(group_kendaraan=f["golongan"])
    for baris in _rentang(kendaraan, "dibuat_pada", f).order_by().values("ditambahkan_oleh").annotate(n=Count("id")):
        jumlah[baris["ditambahkan_oleh"]]["penambahan"] += baris["n"]
    return jumlah


def _total(jumlah, user_ids):
    return {jenis: sum(jumlah[u][jenis] for u in user_ids if u in jumlah) for jenis in JENIS}


def _query_filter(request):
    """The report's filter as a query string, carried into the modal and PDF."""
    return urlencode({k: request.GET[k] for k in ("dari", "sampai", "golongan") if request.GET.get(k)})


@login_required
def laporan_tim(request):
    f = _filter(request)
    tim = _tim()
    user_ids = [n.user_id for ketua, anggota in tim for n in (ketua, *anggota)]
    jumlah = _jumlah_per_akun(f, user_ids)
    query = _query_filter(request)
    rows, tautan = [], []
    for ketua, anggota in tim:
        total = _total(jumlah, [n.user_id for n in (ketua, *anggota)])
        rows.append((
            ketua.user.username, len(anggota), total["pemeriksaan"], total["perbaikan"], total["penambahan"],
            sum(total.values()),
        ))
        url = reverse("accounts:laporan_tim_detail", args=[ketua.pk])
        tautan.append(f"{url}?{query}" if query else url)
    header = ["Ketua Tim", "Jumlah Anggota", "Pemeriksaan", "Perbaikan", "Penambahan Kendaraan", "Total Kegiatan"]
    return _render(
        request, "accounts/laporan_tabel.html", "Laporan Tim", header, rows, f, "laporan-tim.xlsx",
        tautan=tautan, kolom_tanggal=0, kolom_utama=1,
    )


def _aktivitas(f, users):
    """The team's newest activity (at most MAKS_AKTIVITAS) as dicts, newest first."""
    akun = {u.pk: u for u in users}
    daftar = []
    for kode, cfg in _golongan_dipilih(f):
        label = Vehicle.GroupKendaraan(kode).label
        pemeriksaan = _rentang(
            cfg.pemeriksaan_model.objects.filter(pemeriksa__akun__in=list(akun)).select_related("vehicle", "pemeriksa"),
            "dibuat_pada", f,
        ).order_by("-dibuat_pada", "-id")[:MAKS_AKTIVITAS]
        for h in pemeriksaan:
            daftar.append({
                "waktu": h.dibuat_pada, "kegiatan": "Pemeriksaan", "kendaraan": h.vehicle.nopol, "golongan": label,
                "rincian": h.get_macam_pemeriksaan_display(), "personil": h.pemeriksa, "akun": akun[h.pemeriksa.akun_id],
            })
        perbaikan = _rentang(
            cfg.perbaikan_model.objects.filter(teknisi__akun__in=list(akun))
            .select_related("item__pemeriksaan__vehicle", "teknisi"),
            "dibuat_pada", f,
        ).order_by("-dibuat_pada", "-id")[:MAKS_AKTIVITAS]
        for p in perbaikan:
            daftar.append({
                "waktu": p.dibuat_pada, "kegiatan": "Perbaikan", "kendaraan": p.item.pemeriksaan.vehicle.nopol,
                "golongan": label, "rincian": f"{p.item.nomor}. {p.item.nama_alat} → {p.get_kondisi_display()}",
                "personil": p.teknisi, "akun": akun[p.teknisi.akun_id],
            })
    kendaraan = Vehicle.objects.filter(ditambahkan_oleh__in=list(akun)).select_related("penambah")
    if f["golongan"]:
        kendaraan = kendaraan.filter(group_kendaraan=f["golongan"])
    for v in _rentang(kendaraan, "dibuat_pada", f).order_by("-dibuat_pada", "-id")[:MAKS_AKTIVITAS]:
        daftar.append({
            "waktu": v.dibuat_pada, "kegiatan": "Penambahan", "kendaraan": v.nopol,
            "golongan": v.get_group_kendaraan_display(), "rincian": v.merek, "personil": v.penambah,
            "akun": akun[v.ditambahkan_oleh_id],
        })
    daftar.sort(key=lambda a: a["waktu"], reverse=True)
    return daftar[:MAKS_AKTIVITAS]


def konteks_tim(request, pk):
    """Everything the team modal and its PDF show."""
    f = _filter(request)
    ketua = get_object_or_404(Anggota.get_root_nodes().select_related("user"), pk=pk)
    anggota = list(ketua.get_children().select_related("user").order_by("user__username"))
    users = list(
        User.objects.filter(pk__in=[n.user_id for n in (ketua, *anggota)]).prefetch_related("groups")
    )
    urutan = {n.user_id: i for i, n in enumerate((ketua, *anggota))}
    users.sort(key=lambda u: urutan[u.pk])
    jumlah = _jumlah_per_akun(f, list(urutan))
    for u in users:
        u.keanggotaan = keanggotaan_label(u)
        u.jumlah = jumlah[u.pk] if u.pk in jumlah else dict.fromkeys(JENIS, 0)
    return {
        "ketua": ketua.user,
        "anggota": users,
        "total": _total(jumlah, list(urutan)),
        "aktivitas": _aktivitas(f, users),
        "maks_aktivitas": MAKS_AKTIVITAS,
        "keterangan_filter": _keterangan_filter(f),
        "jumlah_anggota": len(anggota),
        "url_pdf": f"{reverse('accounts:laporan_tim_pdf', args=[pk])}?{_query_filter(request)}",
    }


@login_required
def laporan_tim_detail(request, pk):
    return render(request, "accounts/_laporan_tim_detail.html", konteks_tim(request, pk))

