"""Superuser menus Hacking Activity (events, blacklist) and Maintenance (accounts.keamanan)."""
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from . import keamanan
from .models import AktivitasMencurigakan, IpBlokir, Pemeliharaan
from .paging import halaman


def _superuser(request):
    if not request.user.is_superuser:
        raise Http404


def _aktivitas(request):
    qs = AktivitasMencurigakan.objects.select_related("user")
    jenis, tingkat, ip = request.GET.get("jenis", ""), request.GET.get("tingkat", ""), request.GET.get("ip", "").strip()
    if jenis in AktivitasMencurigakan.Jenis.values:
        qs = qs.filter(jenis=jenis)
    if tingkat in AktivitasMencurigakan.Tingkat.values:
        qs = qs.filter(tingkat=tingkat)
    if ip:
        qs = qs.filter(ip__startswith=ip)
    return qs


def _konteks(request):
    sehari = timezone.now() - datetime.timedelta(hours=24)
    terakhir = AktivitasMencurigakan.objects.filter(waktu__gte=sehari)
    ringkas = terakhir.aggregate(semua=Count("id"), tinggi=Count("id", filter=Q(tingkat="tinggi")))
    teratas = list(terakhir.values("ip").annotate(n=Count("id")).order_by("-n")[:5])
    diblokir = {str(b.alamat) for b in IpBlokir.objects.all()}
    hal = halaman(request, _aktivitas(request), per_halaman=25)
    for a in hal:
        a.sudah_diblokir = a.ip in diblokir
    return {
        # Two tabs (?tab=): the events, and the blacklist.
        "tab": "blokir" if request.GET.get("tab") == "blokir" else "aktivitas",
        "blokir_otomatis": getattr(__import__("django.conf").conf.settings, "KEAMANAN_BLOKIR_OTOMATIS", False),
        "ringkas": ringkas,
        "teratas": teratas,
        "halaman": hal,
        "daftar_blokir": IpBlokir.objects.select_related("dibuat_oleh"),
        "jenis_pilihan": AktivitasMencurigakan.Jenis.choices,
        "tingkat_pilihan": AktivitasMencurigakan.Tingkat.choices,
        "f": {k: request.GET.get(k, "") for k in ("jenis", "tingkat", "ip")},
    }


@login_required
def aktivitas_view(request):
    _superuser(request)
    return render(request, "keamanan/aktivitas.html", _konteks(request))


@login_required
def aktivitas_tabel(request):
    """The live part of the page, fetched again on every new event."""
    _superuser(request)
    return render(request, "keamanan/_aktivitas_isi.html", _konteks(request))


@login_required
@require_POST
def blokir_tambah(request):
    _superuser(request)
    alamat = keamanan.alamat_sah(request.POST.get("alamat", ""))
    if alamat is None:
        messages.error(request, "Alamat IP atau rentang CIDR tidak valid.")
    elif keamanan.memuat_alamat_penting(alamat, keamanan.ip_klien(request)):
        messages.error(request, f"{alamat} tidak bisa diblokir: memuat alamat Anda sendiri atau server ini.")
    else:
        _, baru = IpBlokir.objects.update_or_create(alamat=alamat, defaults={
            "alasan": request.POST.get("alasan", "").strip()[:200] or "Diblokir manual", "otomatis": False,
            "sampai": None, "dibuat_oleh": request.user,
        })
        keamanan.segarkan_blokir()
        messages.success(request, f"{alamat} diblokir.")
    return _kembali(request)


def _kembali(request):
    """Back to the tab the form was sent from (Blacklist IP unless it says so)."""
    tab = "aktivitas" if request.POST.get("tab") == "aktivitas" else "blokir"
    return redirect(f"{reverse('accounts:keamanan')}?tab={tab}")


@login_required
@require_POST
def blokir_hapus(request, pk):
    _superuser(request)
    baris = get_object_or_404(IpBlokir, pk=pk)
    baris.delete()
    keamanan.segarkan_blokir()
    messages.success(request, f"Blokir {baris.alamat} dibuka.")
    return _kembali(request)


@login_required
def pemeliharaan_view(request):
    _superuser(request)
    baris = Pemeliharaan.objects.first() or Pemeliharaan()
    if request.method == "POST":
        baris.aktif = request.POST.get("aktif") == "1"
        baris.pesan = request.POST.get("pesan", "").strip()[:300]
        try:
            selesai = parse_datetime(request.POST.get("perkiraan_selesai", "").strip())
        except ValueError:  # well-formed but impossible, e.g. month 13
            selesai = None
        baris.perkiraan_selesai = timezone.make_aware(selesai) if selesai and timezone.is_naive(selesai) else selesai
        baris.diubah_oleh = request.user
        baris.save()
        keamanan.lupakan_pemeliharaan()
        if baris.aktif:
            messages.warning(request, "Mode maintenance AKTIF: selain superuser, semua pengguna melihat halaman pemeliharaan.")
        else:
            messages.success(request, "Mode maintenance dimatikan: aplikasi terbuka lagi untuk semua.")
        return redirect("accounts:pemeliharaan")
    return render(request, "keamanan/pemeliharaan_atur.html", {"baris": baris})
