import datetime
import json
import secrets
import string
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST, require_http_methods

from fleet.images import compress_photo
from fleet.models import Vehicle

from . import dashboard, golongan, km_jadwal, pemeriksaan, pimpinan_tim, roles, status
from .forms import TEXT_INPUT_CLASSES, clean_foto, terapkan_keanggotaan, BiodataForm, GantiPasswordForm, UbahTimForm, SatuanForm, LaporanForm, LoginForm, UserCreateForm, UserEditForm, VpnForm
from .models import Anggota, DraftPemeriksaan, DraftPerbaikan, Laporan, PekerjaanAktif, Satuan, VpnPeer
from .paging import halaman
from .roles import keanggotaan_label


def _get_success_url(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return resolve_url(roles.home_view_name(request.user))


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_get_success_url(request))

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            request.session.set_expiry(1209600 if form.cleaned_data.get("remember_me") else 0)

            success_url = _get_success_url(request)
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect("accounts:login")


def _matra_terkunci(user):
    """The one matra an Admin's or a Pimpinan Tim's dashboard shows, their
    own ("" when they have none). A superuser and a Pimpinan pick any."""
    if user.is_superuser or roles.keanggotaan_kode(user) not in (roles.ADMIN_ROLE, roles.PIMPINAN_TIM):
        return ""
    return getattr(getattr(user, "publik", None), "matra", "")


def _matra_dashboard(request):
    """The matra picked above the dashboard's tabs (?matra=), or "" for all;
    an Admin and a Pimpinan Tim get their own, with no picker."""
    terkunci = _matra_terkunci(request.user)
    if terkunci:
        return terkunci
    matra = request.GET.get("matra", "")
    return matra if matra in dict(roles.MATRA) else ""


def _cakupan_dashboard(request):
    # An admin or Ketua Tim sees their own branch only (dashboard.cakupan),
    # and the dashboard can be narrowed to one matra.
    return dashboard.cakupan_matra(request.user, _matra_dashboard(request))


def _dashboard_context(request):
    return {
        **dashboard.konteks(_cakupan_dashboard(request), request.GET.get("hal_kegiatan")),
        "matra_dashboard": _matra_dashboard(request),
        "matra_pilihan": [] if _matra_terkunci(request.user) else [("", "Semua Matra"), *roles.MATRA],
    }


@login_required
def dashboard_view(request):
    # The Grafik tab and the per-Satuan section are only in the full page;
    # the 10 s refresh swaps just the summary.
    grafik = dashboard.grafik(_cakupan_dashboard(request))
    return render(request, "accounts/dashboard.html", {
        **_dashboard_context(request), "grafik": grafik,
        # Per sub-tab: its units' numbers and its vehicle groups (the columns of a card's table).
        # The Rusak/Tidak Bisa Diperbaiki tab: (vehicles, how many there are).
        "rusak_berat": dashboard.rusak_berat(_cakupan_dashboard(request)),
        "sparepart_rusak": dashboard.sparepart_rusak(_cakupan_dashboard(request)),
        # Semua Matra (no matra picked): one pie of the vehicles per matra and
        # a summary row per matra, instead of the tabs.
        "ringkasan_matra": (
            None if _matra_dashboard(request) else dashboard.ringkasan_matra(request.user, dashboard.KENDARAAN_KODE)
        ),
        "status_satuan": [
            (sub, grafik[sub]["status_satuan"], [
                {"kode": str(kode), "label": label} for kode, label in Vehicle.GroupKendaraan.choices if kode in kodes
            ])
            for sub, kodes in (("kendaraan", dashboard.KENDARAAN_KODE), ("non_kendaraan", dashboard.NON_KENDARAAN_KODE))
        ],
    })


@login_required
def dashboard_kendaraan(request):
    """Modal behind a summary card: the vehicles it counts (?kartu=, ?non=1
    for the Non Kendaraan tab), in the viewer's scope, searched with ?q= and
    paged like every table, with a chart of them per Satuan."""
    kartu = request.GET.get("kartu", "")
    if kartu not in dashboard.KARTU_KENDARAAN:
        raise Http404
    cari = request.GET.get("q", "").strip()
    non = bool(request.GET.get("non"))
    judul, daftar, alasan = dashboard.kendaraan_kartu(kartu, non, _cakupan_dashboard(request), cari)
    # The pie counts every unit; clicking a slice (?satuan=) narrows the table.
    grafik = dashboard.satuan_pie(daftar)
    daftar, satuan_nama = dashboard.saring_satuan(daftar, request.GET.get("satuan", ""))
    page = halaman(request, daftar)
    terakhir = dashboard.pemeriksaan_terakhir(page)
    for vehicle in page:
        vehicle.alasan_servis = alasan.get(vehicle.pk, "")
        vehicle.pemeriksaan_terakhir = terakhir.get(vehicle.pk)
    return render(request, "accounts/_dashboard_kendaraan_modal.html", {
        "judul": judul, "halaman": page, "kartu": kartu, "non": non, "cari": cari,
        "pakai_alasan": kartu == "perlu_servis",
        "grafik": grafik, "satuan": request.GET.get("satuan", "") if satuan_nama else "", "satuan_nama": satuan_nama,
    })


@login_required
def dashboard_rusak_pdf(request):
    """The Rusak/Tidak Bisa Diperbaiki tab as a PDF: its Sparepart table
    (?jenis=sparepart) or its Kendaraan one, in the viewer's scope and matra,
    narrowed like the tab's filter (?dari=, ?sampai=, ?nopol=). Every row,
    not just the newest the tab shows."""
    from . import laporan_pdf
    from .laporan import _tanggal

    dari, sampai = _tanggal(request.GET.get("dari")), _tanggal(request.GET.get("sampai"))
    nopol = request.GET.get("nopol", "").strip().lower()
    users = _cakupan_dashboard(request)

    def lolos(vehicle, waktu):
        if nopol and nopol not in vehicle.nopol.lower():
            return False
        if not (dari or sampai):
            return True
        if waktu is None:
            return False
        tanggal = timezone.localtime(waktu).date()
        return not (dari and tanggal < dari) and not (sampai and tanggal > sampai)

    def satuan(vehicle):
        return vehicle.penambah.satuan.nama if vehicle.penambah and vehicle.penambah.satuan else "-"

    def kapan(waktu):
        return timezone.localtime(waktu).strftime("%d-%m-%Y %H:%M") if waktu else "-"

    if request.GET.get("jenis") == "sparepart":
        judul, nama_file = "SPAREPART RUSAK / TIDAK BISA DIPERBAIKI", "sparepart-rusak.pdf"
        kepala = ["Sparepart / Komponen", "No. Registrasi", "Merk/Type", "Golongan", "Satuan", "Sumber", "Tanggal", "Oleh", "Keterangan"]
        lebar = [10, 45, 27, 30, 24, 40, 24, 22, 20, 25]
        rows = [
            [
                f"{b['item'].nomor}. {b['item'].nama_alat}", b["vehicle"].nopol, b["vehicle"].merek,
                b["vehicle"].get_group_kendaraan_display(), satuan(b["vehicle"]),
                "Perbaikan" if b["perbaikan"] else "Pemeriksaan", kapan(b["waktu"]),
                b["perbaikan"].teknisi.nama if b["perbaikan"] else b["periksa"].pemeriksa.nama, b["keterangan"] or "-",
            ]
            for b in dashboard.sparepart_rusak(users, batas=None)[0] if lolos(b["vehicle"], b["waktu"])
        ]
    else:
        judul, nama_file = "KENDARAAN RUSAK / TIDAK BISA DIPERBAIKI", "kendaraan-rusak.pdf"
        kepala = ["No. Registrasi", "Merk/Type", "Golongan", "Satuan", "Kepemilikan", "Sumber", "Tanggal", "Oleh", "Keterangan"]
        lebar = [10, 30, 34, 24, 44, 24, 24, 22, 22, 33]
        rows = []
        for v in dashboard.rusak_berat(users, batas=None)[0]:
            if not lolos(v, v.waktu_rusak):
                continue
            if v.dinyatakan:
                sumber, oleh, ket = "Form Rusak", v.dinyatakan.pelapor.nama, v.dinyatakan.alasan
            else:
                sumber = "Pemeriksaan"
                oleh = v.periksa.pemeriksa.nama if v.periksa else "-"
                ket = getattr(v.periksa, "keterangan", "") or "-"
            rows.append([
                v.nopol, v.merek, v.get_group_kendaraan_display(), satuan(v), v.get_kepemilikan_display(),
                sumber, kapan(v.waktu_rusak), oleh, ket,
            ])
    keterangan = [dict(roles.MATRA).get(_matra_dashboard(request), "Semua Matra")]
    if dari or sampai:
        keterangan.append(
            f"Periode {dari.strftime('%d-%m-%Y') if dari else 'awal'} s/d {sampai.strftime('%d-%m-%Y') if sampai else 'sekarang'}"
        )
    if nopol:
        keterangan.append(f"No. Registrasi mengandung \"{request.GET.get('nopol', '').strip()}\"")
    return laporan_pdf._pdf_response(
        request, laporan_pdf.buat_pdf_tabel(judul, " · ".join(keterangan), kepala, lebar, rows), nama_file,
    )


def _kelola_tim(request, kode, ketua):
    """Whether the user manages the team of the Ketua Tim node ``ketua``
    (None: not in a team): a superuser any, an Admin their own Ketua Tim's,
    and a Ketua Tim their own team."""
    if ketua is None:
        return False
    if request.user.is_superuser:
        return True
    if kode == roles.ADMIN_ROLE:
        return ketua.admin_id == request.user.pk
    return kode == roles.KETUA_TIM and ketua.user_id == request.user.pk


def _ketua_dari(user):
    """The Ketua Tim node of a Tim member, or None."""
    node = Anggota.objects.filter(user=user).first()
    return node.get_parent() if node is not None and not node.is_root() else None


def _boleh_vpn(request, kode, target):
    """Who handles ``target``'s VPN: a superuser for anyone, an Admin inside
    their own teams (Ketua Tim included), a Ketua Tim for their members."""
    if kode == roles.ADMIN_ROLE:
        node = Anggota.objects.filter(user=target).first()
        return node is not None and _kelola_tim(request, kode, node if node.is_root() else node.get_parent())
    if kode == roles.KETUA_TIM:
        return _kelola_tim(request, kode, _ketua_dari(target))
    return request.user.is_superuser


def _boleh_lihat_vpn(request, target):
    """Reading a WireGuard config: whoever handles the peer, and its owner."""
    return target == request.user or _boleh_vpn(request, roles.keanggotaan_kode(request.user), target)


@login_required
def vpn_config_view(request, user_uid):
    """Modal with a peer's WireGuard config: QR code, text to copy, download."""
    target = get_object_or_404(User, publik__uuid=user_uid)
    if not _boleh_lihat_vpn(request, target):
        return HttpResponse(status=403)
    get_object_or_404(VpnPeer, user=target)
    return render(request, "accounts/_vpn_config.html", {"target": target, **_vpn_context(target, selalu=True)})


@login_required
def vpn_download_view(request, user_uid):
    from django.conf import settings as djsettings
    target = get_object_or_404(User, publik__uuid=user_uid)
    if not _boleh_lihat_vpn(request, target):
        return HttpResponse(status=403)
    vpn = get_object_or_404(VpnPeer, user=target)
    config = vpn.wireguard_config(
        server_endpoint=djsettings.VPN_SERVER_ENDPOINT,
        server_pubkey=djsettings.VPN_SERVER_PUBKEY,
        dns=djsettings.VPN_DNS,
        allowed_ips=djsettings.VPN_ALLOWED_IPS,
    )
    resp = HttpResponse(config, content_type="text/plain")
    resp["Content-Disposition"] = f'attachment; filename="{target.username}.conf"'
    return resp


def _vpn_context(user, selalu=False):
    """``selalu``: build the config even while the server side is not set,
    so the modal can show what is there next to its warning."""
    from django.conf import settings
    vpn = getattr(user, "vpn_peer", None)
    config_text = qr_img = ""
    endpoint = getattr(settings, "VPN_SERVER_ENDPOINT", "")
    pubkey = getattr(settings, "VPN_SERVER_PUBKEY", "")
    if vpn and vpn.private_key and (selalu or (endpoint and pubkey)):
        from .vpn_utils import config_qr_img
        config_text = vpn.wireguard_config(
            endpoint, pubkey,
            dns=getattr(settings, "VPN_DNS", ""),
            allowed_ips=getattr(settings, "VPN_ALLOWED_IPS", "0.0.0.0/0, ::/0"),
        )
        qr_img = config_qr_img(config_text)
    return {
        "vpn": vpn, "config_text": config_text, "qr_img": qr_img,
        "server_configured": bool(endpoint and pubkey) if selalu else bool(endpoint),
    }


@login_required
def info_profile_view(request):
    user = request.user
    laporan = Laporan.objects.filter(akun=user).order_by("-dibuat_pada").first()
    ctx = _vpn_context(user)
    ctx.update({
        "laporan": laporan,
        "keanggotaan": roles.keanggotaan_label(user),
    })
    return render(request, "accounts/info_profile.html", ctx)


@login_required
def info_profile_edit_view(request):
    user = request.user
    laporan = Laporan.objects.filter(akun=user).order_by("-dibuat_pada").first()
    if request.method == "POST":
        form = BiodataForm(request.POST, request.FILES, instance=laporan)
        form.fields["foto"].required = not (laporan and laporan.foto)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.akun = user
            if request.FILES.get("foto"):
                obj.foto = compress_photo(request.FILES["foto"])
            elif laporan and laporan.foto:
                obj.foto = laporan.foto
            obj.save()
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("accounts:info_profile")
            return response
        return render(request, "accounts/_info_profile_edit.html", {"form": form})
    form = BiodataForm(instance=laporan)
    form.fields["foto"].required = not (laporan and laporan.foto)
    return render(request, "accounts/_info_profile_edit.html", {"form": form, "laporan": laporan})


@login_required
def anggota_tim_view(request):
    kode = roles.keanggotaan_kode(request.user)
    is_admin = request.user.is_superuser or kode in roles.ADMIN
    is_ketua = kode == roles.KETUA_TIM
    admin_tim = kode == roles.ADMIN_ROLE  # an Admin sees the teams under them
    # A Pimpinan Tim sees (and doesn't manage) the teams they picked.
    terlihat = pimpinan_tim.tim_terlihat(request.user)

    nodes = list(Anggota.get_tree().select_related("user", "user__vpn_peer", "user__publik"))
    all_user_ids = [n.user_id for n in nodes]
    nip_per_akun = {}
    nama_per_akun = {}
    for akun_id, nip, nama in Laporan.objects.filter(akun__in=all_user_ids).values_list("akun_id", "nip", "nama"):
        nip_per_akun[akun_id] = nip
        nama_per_akun[akun_id] = nama
    baris = []
    for kn in sorted((n for n in nodes if n.depth == 1), key=lambda n: n.user.username):
        # A Ketua Tim sees their own team, an Admin the teams under them.
        if (is_ketua or admin_tim) and not _kelola_tim(request, kode, kn):
            continue
        if terlihat is not None and kn.pk not in terlihat:
            continue
        anak = sorted(
            (n for n in nodes if n.depth == 2 and n.path.startswith(kn.path)),
            key=lambda n: n.user.username,
        )
        dapat_kelola = True if (is_ketua or admin_tim) else is_admin
        baris.append({
            "user": kn.user, "kedalaman": 0, "anggota_pk": kn.pk, "anggota_uuid": kn.uuid,
            "jumlah_anggota": len(anak), "dapat_kelola": dapat_kelola, "keanggotaan": "Ketua Tim",
            # A Ketua Tim's own VPN is handled by the admins above them.
            "dapat_hapus_vpn": dapat_kelola and not is_ketua,
            "nip": nip_per_akun.get(kn.user_id, ""),
            "nama": nama_per_akun.get(kn.user_id, ""),
        })
        for an in anak:
            baris.append({
                "user": an.user, "kedalaman": 1, "ketua_pk": kn.pk,
                "ketua_nama": nama_per_akun.get(kn.user_id, "") or kn.user.username,
                "dapat_kelola": dapat_kelola, "keanggotaan": keanggotaan_label(an.user),
                "dapat_hapus_vpn": dapat_kelola,
                "anggota_tambah_pk": kn.pk,
                "nip": nip_per_akun.get(an.user_id, ""),
                "nama": nama_per_akun.get(an.user_id, ""),
            })
    return render(request, "accounts/anggota_tim.html", {
        "baris": baris,
        "dapat_kelola_global": is_admin or is_ketua,
        # Pimpinan Tim: the button to pick their Ketua Tim.
        "pilih_bawahan_url": (
            reverse("accounts:pimpinan_tim_bawahan", args=[request.user.publik.uuid]) if terlihat is not None else ""
        ),
    })


@login_required
def anggota_tim_tambah_view(request, ketua_uid):
    kode = roles.keanggotaan_kode(request.user)
    ketua = get_object_or_404(Anggota, uuid=ketua_uid, depth=1)
    if not _kelola_tim(request, kode, ketua):
        return HttpResponse(status=403)
    if request.method == "POST":
        form = UserCreateForm(request.POST, ketua=ketua)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Redirect"] = reverse("accounts:anggota_tim")
                return resp
            return redirect("accounts:anggota_tim")
    else:
        form = UserCreateForm(ketua=ketua)
    return render(request, "accounts/_anggota_tim_tambah.html", {"form": form, "ketua": ketua})


@login_required
def anggota_tim_ubah_view(request, user_uid):
    kode = roles.keanggotaan_kode(request.user)
    target = get_object_or_404(User, publik__uuid=user_uid)
    ketua = _ketua_dari(target)
    if ketua is None:
        raise Http404
    if not _kelola_tim(request, kode, ketua):
        return HttpResponse(status=403)
    # An inspection still in progress (an auto-saved draft) belongs to the
    # member's current role: moving them now would strand it, so refuse.
    belum_selesai = list(
        DraftPemeriksaan.objects.filter(pemeriksa=target).select_related("vehicle").order_by("-diperbarui_pada")
    )
    if belum_selesai:
        return render(request, "accounts/_anggota_tim_ubah_blokir.html", {
            "target": target, "belum_selesai": belum_selesai,
        })
    if request.method == "POST":
        form = UbahTimForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                terapkan_keanggotaan(target, form.cleaned_data["keanggotaan"], ketua)
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Redirect"] = reverse("accounts:anggota_tim")
                return resp
            return redirect("accounts:anggota_tim")
    else:
        form = UbahTimForm(initial={"keanggotaan": roles.keanggotaan_kode(target)})
    return render(request, "accounts/_anggota_tim_ubah.html", {"form": form, "target": target, "ketua": ketua})


@login_required
def anggota_tim_vpn_view(request, user_uid):
    target = get_object_or_404(User, publik__uuid=user_uid)
    if not _boleh_vpn(request, roles.keanggotaan_kode(request.user), target):
        return HttpResponse(status=403)
    from django.conf import settings as djsettings
    from .vpn_utils import config_qr_img
    vpn = VpnPeer.objects.filter(user=target).first()
    initial = {
        "peer_name": vpn.peer_name if vpn else "",
        "client_ip": vpn.client_ip if vpn else "",
        "preshared_key": vpn.preshared_key if vpn else "",
    }
    if request.method == "POST":
        form = VpnForm(request.POST, initial=initial, user=target)
        if form.is_valid():
            form.save(target)
            if request.headers.get("HX-Request") == "true":
                resp = HttpResponse(status=204)
                resp["HX-Redirect"] = reverse("accounts:anggota_tim")
                return resp
            return redirect("accounts:anggota_tim")
    else:
        form = VpnForm(initial=initial, user=target)

    # Build config preview and QR if keys exist
    qr_img = config_text = ""
    server_ep = djsettings.VPN_SERVER_ENDPOINT
    server_pk = djsettings.VPN_SERVER_PUBKEY
    if vpn and vpn.private_key and server_ep and server_pk:
        config_text = vpn.wireguard_config(
            server_endpoint=server_ep,
            server_pubkey=server_pk,
            dns=djsettings.VPN_DNS,
            allowed_ips=djsettings.VPN_ALLOWED_IPS,
        )
        qr_img = config_qr_img(config_text)

    return render(request, "accounts/_anggota_tim_vpn.html", {
        "form": form, "target": target,
        "vpn": vpn, "config_text": config_text, "qr_img": qr_img,
        "server_configured": bool(server_ep and server_pk),
    })


@login_required
def anggota_tim_vpn_hapus_view(request, user_uid):
    """Hapus VPN on the Anggota Tim page: removing a member's VPN removes the
    member, account and all. GET: confirmation with a code to retype. POST:
    delete."""
    target = get_object_or_404(User, publik__uuid=user_uid)
    if not _boleh_vpn(request, roles.keanggotaan_kode(request.user), target):
        return HttpResponse(status=403)
    vpn = get_object_or_404(VpnPeer, user=target)
    node = Anggota.objects.filter(user=target).first()
    pesan = None
    if target.is_superuser or target == request.user:
        pesan = f"User {target.username} tidak bisa dihapus."
    elif node is not None and node.get_children_count():
        pesan = f"Ketua Tim {target.username} masih punya anggota. Hapus atau pindahkan anggotanya dulu."
    if pesan:
        return render(request, "accounts/_user_delete_blocked.html", {
            "akun": target, "keanggotaan": keanggotaan_label(target), "pesan": pesan,
        })
    session_key = f"delete_captcha_{target.pk}"
    if request.method == "POST":
        kode_benar = request.session.get(session_key)
        if not kode_benar or request.POST.get("captcha", "").strip() != kode_benar:
            messages.error(request, "Kode verifikasi salah.")
            return redirect("accounts:anggota_tim")
        del request.session[session_key]
        with transaction.atomic():
            # Delete the tree node through treebeard so the parent's child count stays right.
            if node is not None:
                node.delete()
            target.delete()
        messages.success(request, f"VPN dan akun {target.username} berhasil dihapus.")
        return redirect("accounts:anggota_tim")
    kode = "".join(secrets.choice(string.digits) for _ in range(6))
    request.session[session_key] = kode
    return render(request, "accounts/_vpn_delete_confirm.html", {
        "target": target, "vpn": vpn, "keanggotaan": keanggotaan_label(target), "captcha_kode": kode,
    })


@login_required
def anggota_tim_aktif_view(request, user_uid):
    """Nonaktifkan / Aktifkan on the Anggota Tim page. A switched-off account
    stays, with its data and its VPN connection, but can't log in to the app
    until it is switched on again. GET: confirmation. POST: flip."""
    target = get_object_or_404(User, publik__uuid=user_uid)
    if target.is_superuser or target == request.user or not _boleh_vpn(
        request, roles.keanggotaan_kode(request.user), target,
    ):
        return HttpResponse(status=403)
    if request.method == "POST":
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        messages.success(request, f"User {target.username} {'diaktifkan' if target.is_active else 'dinonaktifkan'}.")
        return redirect("accounts:anggota_tim")
    return render(request, "accounts/_anggota_aktif_confirm.html", {
        "target": target, "keanggotaan": keanggotaan_label(target),
    })


@login_required
def dashboard_partial(request):
    return render(request, "accounts/_dashboard_content.html", _dashboard_context(request))


def password_reset_placeholder(request):
    return render(request, "accounts/password_reset_placeholder.html")


def _kendaraan_dari_uuid(nilai):
    """The Vehicle whose public uuid is ``nilai`` (posted by the forms), or None."""
    try:
        return Vehicle.objects.filter(uuid=uuid.UUID(nilai or "")).first()
    except ValueError:
        return None


CAPTCHA_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")


def _new_captcha_code():
    return "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(6))


@login_required
def laporan_view(request):
    laporan_user = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    pemeriksaan_form = None
    captcha_error = ""

    if request.method == "POST":
        expected = request.session.get("laporan_captcha", "")
        captcha = request.POST.get("captcha", "").strip().upper()
        captcha_ok = bool(expected and captcha == expected)

        if not captcha_ok:
            gagal = request.session.get("laporan_captcha_gagal", 0) + 1
            request.session["laporan_captcha_gagal"] = gagal
            if gagal >= CAPTCHA_MAX_GAGAL:
                code = _new_captcha_code()
                request.session["laporan_captcha"] = code
                request.session["laporan_captcha_gagal"] = 0
                captcha_error = "Terlalu banyak percobaan. Kode baru sudah dibuat."
            else:
                captcha_error = "Kode keamanan tidak sesuai."

        vehicle = _kendaraan_dari_uuid(request.POST.get("vehicle"))
        golongan_cfg = golongan.for_vehicle(vehicle) or golongan.GOLONGAN[Vehicle.GroupKendaraan.GOLONGAN_B]
        pemeriksaan_form = golongan_cfg.form(request.POST, request.FILES)

        if captcha_ok and laporan_user and pemeriksaan_form.is_valid():
            with transaction.atomic():
                hasil = pemeriksaan_form.save(commit=False)
                hasil.pemeriksa = laporan_user
                hasil.save()
                for item in pemeriksaan_form.cleaned_items:
                    fotos = [compress_photo(f) for f in item.pop("fotos")]
                    golongan_cfg.item_model.objects.create(
                        pemeriksaan=hasil, **golongan_cfg.item_model.kolom_foto(fotos), **item,
                    )
            # The dashboard's Siap / Rusak Ringan / Rusak Berat follow the inspection.
            golongan.perbarui_status(hasil.vehicle)
            DraftPemeriksaan.objects.filter(vehicle=hasil.vehicle, pemeriksa=request.user).delete()
            del request.session["laporan_captcha"]
            messages.success(request, f"Pemeriksaan {hasil.vehicle.nopol} berhasil disimpan.")
            return redirect("accounts:pemeriksaan")

    captcha_code = _new_captcha_code()
    request.session["laporan_captcha"] = captcha_code
    request.session["laporan_captcha_gagal"] = 0
    return render(request, "accounts/laporan.html", {
        "laporan_user": laporan_user,
        "pemeriksaan_form": pemeriksaan_form,
        "captcha_code": captcha_code,
        "captcha_error": captcha_error,
        # Status aktif: an inspection left unsaved reopens with its draft.
        "nopol_lanjut": status.lanjut_pemeriksaan(request.user) if request.method == "GET" else "",
        "golongan_dengan_form": "[" + ", ".join(f"'{str(kode)}'" for kode in golongan.GOLONGAN) + "]",
    })


@login_required
def pemeriksaan_checklist_view(request, kode):
    """The checklist of one vehicle group, loaded into Form Pemeriksaan after the QR scan.

    Loading only the scanned group's checklist keeps the page small and
    keeps other groups' same-named, required fields out of the form.
    """
    cfg = golongan.GOLONGAN.get(kode)
    if cfg is None:
        raise Http404("Form pemeriksaan untuk golongan ini belum tersedia.")
    return render(request, cfg.template, {
        "kondisi": cfg.kondisi,
        # Motor's oil parts are marked * (they go into the Jadwal).
        "alat_bertanda": pemeriksaan.BERMOTOR_KM_NOMOR if kode == Vehicle.GroupKendaraan.KENDARAAN_BERMOTOR else (),
        "pakai_jumlah": cfg.pakai_jumlah,
        "pakai_satuan": cfg.pakai_satuan,
        # Golongan B
        "pembagian_kelas": pemeriksaan.PEMBAGIAN_KELAS,
        "eselon_reparasi": pemeriksaan.ESELON_REPARASI,
        "macam_pemeriksaan": pemeriksaan.MACAM_PEMERIKSAAN,
        "buku_jalan": pemeriksaan.BUKU_JALAN,
        "alat_golongan_b": pemeriksaan.ALAT_BERNOMOR,
        # Motor
        "buku_harian": pemeriksaan.BUKU_HARIAN,
        "alat_bermotor": pemeriksaan.KOMPONEN_BERMOTOR_BERNOMOR,
        "satuan_opsi": [{"v": s.pk, "l": s.nama} for s in Satuan.objects.order_by("nama")],
        # Kendaraan Diesel and Jeep Diesel
        "diesel_bab": cfg.bab,
        "ya_tidak": pemeriksaan.YA_TIDAK,
        "kondisi_ranmor": pemeriksaan.KONDISI_RANMOR,
    })


CAPTCHA_MAX_GAGAL = 5


@login_required
@require_POST
def pemeriksaan_captcha_view(request):
    """Check the Form Pemeriksaan captcha before the (large) form is posted."""
    expected = request.session.get("laporan_captcha", "")
    if expected and request.POST.get("captcha", "").strip().upper() == expected:
        return JsonResponse({"ok": True})
    gagal = request.session.get("laporan_captcha_gagal", 0) + 1
    request.session["laporan_captcha_gagal"] = gagal
    if gagal >= CAPTCHA_MAX_GAGAL:
        # Rotate the code so it can't be brute-forced through this endpoint.
        code = _new_captcha_code()
        request.session["laporan_captcha"] = code
        request.session["laporan_captcha_gagal"] = 0
        return JsonResponse({"ok": False, "error": "Terlalu banyak percobaan. Kode baru sudah dibuat.", "code": code})
    return JsonResponse({"ok": False, "error": "Kode keamanan tidak sesuai."})


# A full diesel checklist with long notes stays well under this.
DRAFT_MAKS_BYTE = 512 * 1024


@login_required
@require_http_methods(["GET", "POST"])
def pemeriksaan_draft_view(request, vehicle_uid):
    """GET: return saved draft JSON for this vehicle + user. POST: upsert draft."""
    vehicle = get_object_or_404(Vehicle, uuid=vehicle_uid)
    if not status.dicatat(request.user):
        # A superuser's form isn't auto-saved, and nothing is left to resume
        # (a draft from before this rule is dropped).
        DraftPemeriksaan.objects.filter(pemeriksa=request.user).delete()
        return JsonResponse({"ok": True} if request.method == "POST" else {})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({"ok": False}, status=400)
        if not isinstance(data, dict) or len(request.body) > DRAFT_MAKS_BYTE:
            return JsonResponse({"ok": False}, status=400)
        DraftPemeriksaan.objects.update_or_create(
            vehicle=vehicle, pemeriksa=request.user,
            defaults={"data": data},
        )
        return JsonResponse({"ok": True})
    draft = DraftPemeriksaan.objects.filter(vehicle=vehicle, pemeriksa=request.user).first()
    return JsonResponse(draft.data if draft else {})


# How long another inspector's draft counts as "being inspected".
PEMERIKSA_LAIN_JAM = 24


@login_required
def pemeriksaan_lain_view(request, vehicle_uid):
    """Who else is inspecting this vehicle: the other users with a draft for
    it touched in the last PEMERIKSA_LAIN_JAM hours, for the form's warning."""
    vehicle = get_object_or_404(Vehicle, uuid=vehicle_uid)
    kini = timezone.now()
    draf = list(
        DraftPemeriksaan.objects
        .filter(vehicle=vehicle, diperbarui_pada__gte=kini - datetime.timedelta(hours=PEMERIKSA_LAIN_JAM))
        .exclude(pemeriksa=request.user).select_related("pemeriksa").order_by("-diperbarui_pada")
    )
    nama = dict(
        Laporan.objects.filter(akun__in=[d.pemeriksa_id for d in draf]).order_by("dibuat_pada")
        .values_list("akun_id", "nama")
    )
    return JsonResponse({"lain": [
        {
            "nama": nama.get(d.pemeriksa_id) or d.pemeriksa.username,
            "menit": int((kini - d.diperbarui_pada).total_seconds() // 60),
        }
        for d in draf
    ]})


@login_required
def form_tambah_view(request):
    laporan_user = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    # Form Group may limit which of these forms this user opens.
    boleh = roles.form_tambah_boleh(request.user)
    # Status aktif: the vehicle form left unsaved reopens.
    lanjut = status.lanjut_penambahan(request.user)
    return render(request, "accounts/form_tambah.html", {
        "golongan_lanjut": lanjut if lanjut in boleh and laporan_user else "",
        "laporan_user": laporan_user,
        "golongan_pilihan": [c for c in Vehicle.GroupKendaraan.choices if c[0] in boleh],
        "boleh_non_kendaraan": "non_kendaraan" in boleh,
        "matra_pilihan": roles.MATRA,
        # Opens on the user's own matra.
        "matra_awal": getattr(getattr(request.user, "publik", None), "matra", "") or roles.MATRA[0][0],
    })


@login_required
def history_view(request):
    return render(request, "accounts/history.html")


def _vehicle_from_scan(request):
    return (
        Vehicle.objects.prefetch_related("fotos")
        .filter(nopol=request.GET.get("nopol", "").strip())
        .first()
    )


def _riwayat_pemeriksaan(vehicle):
    """Inspections of the vehicle's group, newest first, each with
    ``kondisi_counts`` [(kode, label, count)]; plus the latest one."""
    cfg = golongan.for_vehicle(vehicle)
    if cfg is None:
        return [], None
    # kesatuan (Golongan B) is shown in each inspection's summary.
    related = ["pemeriksa"] + [
        f.name for f in cfg.pemeriksaan_model._meta.get_fields() if f.name == "kesatuan"
    ]
    riwayat = list(
        getattr(vehicle, cfg.relasi).select_related(*related)
        .annotate(**{
            f"jumlah_{kode}": Count("items", filter=Q(items__kondisi=kode)) for kode, _ in cfg.kondisi
        })
        # Meta.ordering is dropped on GROUP BY queries, so order explicitly.
        .order_by("-dibuat_pada", "-id")
    )
    for hasil in riwayat:
        hasil.kondisi_counts = [(kode, label, getattr(hasil, f"jumlah_{kode}")) for kode, label in cfg.kondisi]
    return riwayat, (riwayat[0] if riwayat else None)


def _perlu_perbaikan(vehicle, terakhir):
    """Parts of the latest inspection not rated Baik whose latest repair isn't Baik yet.

    Each item gets ``perbaikan_terakhir`` (its most recent repair or None).
    """
    if terakhir is None:
        return []
    cfg = golongan.for_vehicle(vehicle)
    items = terakhir.items.exclude(kondisi__in=cfg.baik).prefetch_related(
        Prefetch("perbaikan", queryset=cfg.perbaikan_model.objects.select_related("teknisi"))
    )
    daftar = []
    for item in items:
        repairs = list(item.perbaikan.all())
        item.perbaikan_terakhir = repairs[0] if repairs else None
        if item.perbaikan_terakhir is None or item.perbaikan_terakhir.kondisi not in cfg.baik:
            daftar.append(item)
    return daftar


def _history_context(vehicle):
    """Context of the History tabs (profile, status, inspections, repairs) for a vehicle."""
    riwayat, terakhir = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None)
    riwayat_perbaikan = []
    cfg = golongan.for_vehicle(vehicle)
    if cfg is not None:
        riwayat_perbaikan = cfg.perbaikan_model.objects.filter(
            item__pemeriksaan__vehicle=vehicle
        ).select_related("item", "teknisi")
    return {
        "vehicle": vehicle,
        "riwayat": riwayat,
        "terakhir": terakhir,
        # Parts repaired back to Baik no longer need attention.
        "perlu_perhatian": _perlu_perbaikan(vehicle, terakhir),
        "riwayat_perbaikan": riwayat_perbaikan,
        "pakai_jumlah": cfg.pakai_jumlah if cfg else False,
        "pakai_satuan": cfg.pakai_satuan if cfg else False,
    }


@login_required
def history_kendaraan_view(request):
    """Inspection and repair history of the vehicle whose QR code was scanned."""
    return render(request, "accounts/_history_kendaraan.html", _history_context(_vehicle_from_scan(request)))


@login_required
def history_kendaraan_modal_view(request):
    """The History tabs for one vehicle, opened from a row of the Armada Cari modal."""
    return render(request, "accounts/_history_modal.html", _history_context(_vehicle_from_scan(request)))


def _clean_perbaikan(data, files, daftar, kondisi, pakai_jumlah):
    """Validate the repair fields of the items the technician opened.

    Returns (entries, errors); entries are dicts ready for the group's repair model.
    """
    kondisi_valid = {kode for kode, _ in kondisi}
    entries, errors = [], []
    for item in daftar:
        prefix = f"perbaikan_{item.pk}_"
        if not data.get(prefix + "aktif"):
            continue
        label = f"{item.nomor}. {item.nama_alat}"
        kode = data.get(prefix + "kondisi", "")
        if kode not in kondisi_valid:
            errors.append(f"Kondisi perbaikan {label} belum dipilih.")
        jumlah_raw = data.get(prefix + "jml", "").strip() if pakai_jumlah else ""
        if jumlah_raw and not jumlah_raw.isdigit():
            errors.append(f"Jumlah perbaikan {label} harus angka 0 atau lebih.")
        fotos = clean_foto(files, prefix + "foto", f"perbaikan {label}", errors)
        entry = {
            "item": item,
            "kondisi": kode,
            "keterangan": data.get(prefix + "keterangan", "").strip(),
            "fotos": fotos,
        }
        if pakai_jumlah:
            entry["jumlah"] = int(jumlah_raw) if jumlah_raw.isdigit() else None
        entries.append(entry)
    if not entries and not errors:
        errors.append("Pilih minimal satu item lalu klik Perbaikan untuk mengisinya.")
    return entries, errors


# A repair repeating the same technician's one for the same part within this
# many seconds is the form sent twice, not a second repair.
PERBAIKAN_GANDA_DETIK = 120


@login_required
def perbaikan_view(request):
    laporan_user = Laporan.objects.filter(akun=request.user).order_by("-dibuat_pada").first()
    errors = []
    if request.method == "POST":
        vehicle = _kendaraan_dari_uuid(request.POST.get("vehicle"))
        cfg = golongan.for_vehicle(vehicle)
        if not laporan_user:
            errors.append("Isi biodata di Info Profil terlebih dahulu.")
        elif cfg is None:
            errors.append("Scan QR Code kendaraan terlebih dahulu.")
        else:
            _, terakhir = _riwayat_pemeriksaan(vehicle)
            entries, errors = _clean_perbaikan(
                request.POST, request.FILES, _perlu_perbaikan(vehicle, terakhir), pemeriksaan.KONDISI_PERBAIKAN, cfg.pakai_jumlah,
            )
        if laporan_user and not errors:
            with transaction.atomic():
                # Simpan sent twice (a second click while the photos upload)
                # must not record the same repair twice.
                baru_saja = timezone.now() - datetime.timedelta(seconds=PERBAIKAN_GANDA_DETIK)
                for entry in entries:
                    if cfg.perbaikan_model.objects.filter(
                        teknisi=laporan_user, item=entry["item"], kondisi=entry["kondisi"],
                        keterangan=entry["keterangan"], dibuat_pada__gte=baru_saja,
                    ).exists():
                        continue
                    fotos = [compress_photo(f) for f in entry.pop("fotos")]
                    cfg.perbaikan_model.objects.create(
                        teknisi=laporan_user, **cfg.perbaikan_model.kolom_foto(fotos), **entry,
                    )
            golongan.perbarui_status(vehicle)  # all parts repaired: Sudah Diperbaiki
            status.selesai(request.user, PekerjaanAktif.Jenis.PERBAIKAN, vehicle)
            DraftPerbaikan.objects.filter(vehicle=vehicle, teknisi=request.user).delete()
            messages.success(request, f"Perbaikan {vehicle.nopol} berhasil disimpan ({len(entries)} item).")
            return redirect(f"{reverse('accounts:perbaikan')}?{urlencode({'nopol': vehicle.nopol})}")
    return render(request, "accounts/perbaikan.html", {
        "laporan_user": laporan_user,
        "perbaikan_errors": errors,
        # Status aktif: a repair left unsaved reopens on its vehicle.
        "nopol": request.GET.get("nopol", "") or status.lanjut_perbaikan(request.user),
    })


@login_required
def perbaikan_draft_view(request, vehicle_uid):
    """Form Perbaikan's auto-save, like Form Pemeriksaan's. GET: the saved
    draft for this vehicle and user. POST: store it."""
    vehicle = get_object_or_404(Vehicle, uuid=vehicle_uid)
    if not status.dicatat(request.user):
        # A superuser's form isn't auto-saved, and nothing is left to resume.
        DraftPerbaikan.objects.filter(teknisi=request.user).delete()
        return JsonResponse({"ok": True} if request.method == "POST" else {})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({"ok": False}, status=400)
        if not isinstance(data, dict) or len(request.body) > DRAFT_MAKS_BYTE:
            return JsonResponse({"ok": False}, status=400)
        DraftPerbaikan.objects.update_or_create(vehicle=vehicle, teknisi=request.user, defaults={"data": data})
        return JsonResponse({"ok": True})
    draft = DraftPerbaikan.objects.filter(vehicle=vehicle, teknisi=request.user).first()
    return JsonResponse(draft.data if draft else {})


@login_required
def perbaikan_kendaraan_view(request):
    """Parts to repair on the scanned vehicle: non-Baik items of its last inspection."""
    vehicle = _vehicle_from_scan(request)
    _, terakhir = _riwayat_pemeriksaan(vehicle) if vehicle else ([], None)
    cfg = golongan.for_vehicle(vehicle)
    daftar = _perlu_perbaikan(vehicle, terakhir)
    if daftar:
        # Shown on the technician's Status menu until the repair is saved or cancelled.
        status.mulai(request.user, PekerjaanAktif.Jenis.PERBAIKAN, vehicle)
    return render(request, "accounts/_perbaikan_daftar.html", {
        "vehicle": vehicle,
        "terakhir": terakhir,
        "daftar": daftar,
        # A repair ends on Baik, Perlu Servis or Rusak, whatever the group's inspection codes.
        "kondisi": [
            (kode, pemeriksaan.SINGKATAN_PERBAIKAN[kode], arti) for kode, arti in pemeriksaan.KONDISI_PERBAIKAN
        ] if cfg else [],
        "pakai_jumlah": cfg.pakai_jumlah if cfg else False,
        "pakai_satuan": cfg.pakai_satuan if cfg else False,
    })


@login_required
def pengaturan_view(request):
    """Users as a tree: Admin > Ketua Tim > Tim member, each level sorted by
    username; users above nobody first, then Ketua Tim without an Admin."""
    semua = {u.pk: u for u in User.objects.prefetch_related("groups").select_related("vpn_peer", "publik").order_by("username")}
    pemilik = _pemilik()
    nodes = list(Anggota.get_tree())
    roots = {n.path: n for n in nodes if n.depth == 1}
    anggota_tim = {n.user_id for n in nodes if n.depth > 1}
    anak = {}
    # Ketua Tim under their Admin (Tim members hang under their Ketua Tim,
    # below).
    for akun_pk, induk_pk in pemilik.items():
        if akun_pk in semua and induk_pk in semua and akun_pk not in anggota_tim:
            anak.setdefault(induk_pk, []).append(semua[akun_pk])
    ketua_tim = {}  # Tim member pk -> their Ketua Tim's username
    for node in nodes:
        akun = semua[node.user_id]
        if node.depth == 1:
            akun.anggota_uuid = node.uuid
        else:
            ketua = semua[roots[node.path[:Anggota.steplen]].user_id]
            ketua_tim[akun.pk] = ketua.username
            anak.setdefault(ketua.pk, []).append(akun)
    punya_induk = {a.pk for daftar in anak.values() for a in daftar}

    users = []

    def tambah(akun, leluhur):
        # leluhur: the collapse keys of the rows above, any of which hides this row.
        akun.kedalaman, akun.leluhur, akun.grup = len(leluhur), leluhur, f"u{akun.pk}"
        akun.ketua_tim = ketua_tim.get(akun.pk, "")
        bawahan = sorted(anak.get(akun.pk, []), key=lambda a: a.username)
        akun.jumlah_anggota = len(bawahan)
        users.append(akun)
        for a in bawahan:
            tambah(a, [*leluhur, akun.grup])

    teratas = [a for a in semua.values() if a.pk not in punya_induk]
    for akun in sorted(teratas, key=lambda a: (hasattr(a, "anggota_uuid"), a.username)):
        tambah(akun, [])
    # Superuser accounts are listed for superusers only.
    if not request.user.is_superuser:
        users = [akun for akun in users if not akun.is_superuser]
    kode_pengelola = roles.keanggotaan_kode(request.user)
    matra = dict(roles.MATRA)
    for akun in users:
        akun.keanggotaan = keanggotaan_label(akun)
        akun.boleh_ubah = _boleh_ubah(request, akun, kode_pengelola, pemilik)
        akun.tambah_url = _tambah_anggota_url(request, akun, kode_pengelola, pemilik)
        # Their own matra; a Ketua Tim or Tim member made before it was asked
        # for shows their Admin's.
        sendiri = getattr(getattr(akun, "publik", None), "matra", "")
        induk = semua.get(pemilik.get(akun.pk))
        akun.matra_label = matra.get(sendiri or getattr(getattr(induk, "publik", None), "matra", ""), "")
        # A superuser picks a Pimpinan Tim's Ketua Tim from their row.
        akun.bawahan_url = (
            reverse("accounts:pimpinan_tim_bawahan", args=[akun.publik.uuid])
            if request.user.is_superuser and akun.keanggotaan == roles.GROUP_NAMES[roles.PIMPINAN_TIM] else ""
        )
    matra_satuan = request.GET.get("matra") if request.GET.get("matra") in dict(roles.MATRA) else "darat"
    jumlah_per_matra = dict(Satuan.objects.order_by().values_list("matra").annotate(n=Count("id")))
    # Each tab pages on its own parameter; a page link also reopens its tab.
    return render(request, "accounts/pengaturan.html", {
        "users": halaman(request, users, param="hal_user", tab="user"),
        # The Satuan tab lists one matra at a time (?matra=).
        "satuan_list": halaman(
            request, Satuan.objects.filter(matra=matra_satuan), param="hal_satuan", tab="satuan", matra=matra_satuan,
        ),
        "matra_satuan": matra_satuan,
        "matra_pilihan": [
            (kode, label, jumlah_per_matra.get(kode, 0)) for kode, label in roles.MATRA
        ],
        "km_list": km_jadwal.daftar(),
        "tab": request.GET.get("tab") if request.GET.get("tab") in ("satuan", "km") else "user",
    })


@login_required
def user_create(request):
    # "+ Anggota" on a row: ?ketua=<Anggota uuid> adds a Tim member under that
    # Ketua Tim, ?admin=<user uuid> a Ketua Tim under that Admin. One the
    # user may not add under is ignored, leaving the plain Tambah User form.
    def uuid_dari(param):
        try:
            return uuid.UUID(request.GET.get(param, ""))
        except ValueError:
            return None

    kode_pengelola = roles.keanggotaan_kode(request.user)
    pemilik = _pemilik()
    ketua = admin = None
    if uid := uuid_dari("ketua"):
        ketua = Anggota.get_root_nodes().select_related("user").filter(uuid=uid).first()
        if ketua is not None and not _boleh_tambah_di(request, ketua.user, roles.KETUA_TIM, kode_pengelola, pemilik):
            ketua = None
    elif uid := uuid_dari("admin"):
        admin = User.objects.filter(publik__uuid=uid, groups__name=roles.GROUP_NAMES[roles.ADMIN_ROLE]).first()
        if admin is not None and not _boleh_tambah_di(request, admin, roles.ADMIN_ROLE, kode_pengelola, pemilik):
            admin = None
    kwargs = {"kode_pengelola": kode_pengelola, "ketua": ketua, "admin": admin}
    if request.method == "POST":
        form = UserCreateForm(request.POST, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserCreateForm(**kwargs)
    is_htmx = request.headers.get("HX-Request") == "true"
    template = "accounts/_user_form_fields.html" if is_htmx else "accounts/user_form.html"
    return render(request, template, {"form": form})


@login_required
def user_delete(request, uid):
    """GET: confirmation for the Pengaturan modal. POST: delete the user.

    Superusers and the logged-in user's own account can't be deleted here.
    """
    akun = get_object_or_404(User, publik__uuid=uid)
    node = getattr(akun, "anggota", None)
    pesan = None
    if akun.is_superuser or not _boleh_ubah(request, akun):
        pesan = f"User {akun.username} tidak bisa dihapus."
    elif node is not None and node.get_children_count():
        pesan = f"Ketua Tim {akun.username} masih punya anggota. Hapus atau pindahkan anggotanya dulu."
    elif Anggota.objects.filter(admin=akun).exists():
        pesan = f"Admin {akun.username} masih punya Ketua Tim. Hapus Ketua Tim-nya dulu."
    if pesan:
        # The Hapus button loads this into the modal: explain there, since a
        # redirect would put the whole Pengaturan page inside the modal.
        if request.headers.get("HX-Request") == "true":
            return render(request, "accounts/_user_delete_blocked.html", {
                "akun": akun, "keanggotaan": keanggotaan_label(akun), "pesan": pesan,
            })
        messages.error(request, pesan)
        return redirect("accounts:pengaturan")
    session_key = f"delete_captcha_{akun.pk}"
    if request.method == "POST":
        kode_benar = request.session.get(session_key)
        kode_input = request.POST.get("captcha", "").strip()
        if not kode_benar or kode_input != kode_benar:
            messages.error(request, "Kode verifikasi salah.")
            return redirect("accounts:pengaturan")
        del request.session[session_key]
        with transaction.atomic():
            # Delete the tree node through treebeard so the parent's child count stays right.
            if node is not None:
                node.delete()
            akun.delete()
        messages.success(request, f"User {akun.username} berhasil dihapus.")
        return redirect("accounts:pengaturan")
    kode = "".join(secrets.choice(string.digits) for _ in range(6))
    request.session[session_key] = kode
    return render(request, "accounts/_user_delete_confirm.html", {
        "akun": akun,
        "keanggotaan": keanggotaan_label(akun),
        "captcha_kode": kode,
    })


def _pemilik():
    """User pk -> pk of the Admin who manages them: a Ketua Tim's (and their
    members') Admin."""
    pemilik = {}
    nodes = list(Anggota.objects.values_list("user_id", "path", "depth", "admin_id"))
    admin_per_root = {path: admin for _, path, depth, admin in nodes if depth == 1}
    for user_id, path, _, _ in nodes:
        if admin := admin_per_root.get(path[:Anggota.steplen]):
            pemilik[user_id] = admin
    return pemilik


def _milik_admin(kode_pengelola, kode):
    """Whether an admin with role ``kode_pengelola`` only manages the users
    with role ``kode`` that are under them (see _pemilik)."""
    return kode_pengelola == roles.ADMIN_ROLE and (kode == roles.KETUA_TIM or kode in roles.TIM)


def _boleh_ubah(request, akun, kode_pengelola=None, pemilik=None):
    """Nobody changes their own role here, admin roles only change from
    higher up (roles.boleh_kelola), and an admin only manages the users under
    them (_milik_admin). ``pemilik`` is _pemilik(), passed to skip queries."""
    if kode_pengelola is None:
        kode_pengelola = roles.keanggotaan_kode(request.user)
    kode = roles.keanggotaan_kode(akun)
    if akun.pk == request.user.pk or not roles.boleh_kelola(kode_pengelola, kode):
        return False
    if _milik_admin(kode_pengelola, kode):
        return (pemilik if pemilik is not None else _pemilik()).get(akun.pk) == request.user.pk
    return True


def _boleh_tambah_di(request, induk, kode_induk, kode_pengelola, pemilik):
    """Whether the user may add someone under ``induk`` (role ``kode_induk``)
    with "+ Anggota": a superuser anywhere; an admin under themselves or
    under someone they manage; anyone else (who reached Pengaturan) only Tim
    members, under a Ketua Tim no Admin owns."""
    if kode_pengelola == roles.SUPERUSER or induk.pk == request.user.pk:
        return True
    if kode_pengelola in roles.ADMIN:
        return _boleh_ubah(request, induk, kode_pengelola, pemilik)
    return kode_induk == roles.KETUA_TIM and induk.pk not in pemilik


def _tambah_anggota_url(request, akun, kode_pengelola, pemilik):
    """Where this Pengaturan row's "+ Anggota" button goes, or None for no button."""
    kode = roles.keanggotaan_kode(akun)
    if kode == roles.KETUA_TIM and getattr(akun, "anggota_uuid", None):
        param = f"ketua={akun.anggota_uuid}"
    elif kode == roles.ADMIN_ROLE:
        param = f"admin={akun.publik.uuid}"
    else:
        return None
    if not _boleh_tambah_di(request, akun, kode, kode_pengelola, pemilik):
        return None
    return f"{reverse('accounts:user_create')}?{param}"


@login_required
def user_reset_password(request, uid):
    """GET: confirmation for the Pengaturan modal. POST: set the user's
    password back to roles.DEFAULT_PASSWORD. For whoever may edit the user."""
    akun = get_object_or_404(User, publik__uuid=uid)
    if not _boleh_ubah(request, akun):
        messages.error(request, f"Password {akun.username} tidak bisa direset.")
        return redirect("accounts:pengaturan")
    if request.method == "POST":
        akun.set_password(roles.DEFAULT_PASSWORD)
        akun.save(update_fields=["password"])
        messages.success(request, f"Password {akun.username} direset ke {roles.DEFAULT_PASSWORD}.")
        return redirect("accounts:pengaturan")
    return render(request, "accounts/_user_reset_password_confirm.html", {
        "akun": akun, "keanggotaan": keanggotaan_label(akun), "password": roles.DEFAULT_PASSWORD,
    })


@login_required
def user_edit(request, uid):
    """Change a user's keanggotaan / Ketua Tim from the Pengaturan modal."""
    akun = get_object_or_404(User, publik__uuid=uid)
    if not _boleh_ubah(request, akun):
        messages.error(request, f"Keanggotaan {akun.username} tidak bisa diubah.")
        return redirect("accounts:pengaturan")
    kode_pengelola = roles.keanggotaan_kode(request.user)
    kwargs = {
        "user": akun, "kode_pengelola": kode_pengelola,
        "admin": request.user if kode_pengelola == roles.ADMIN_ROLE else None,
    }
    if request.method == "POST":
        form = UserEditForm(request.POST, **kwargs)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, f"Keanggotaan {akun.username} berhasil diubah.")
            success_url = reverse("accounts:pengaturan")
            if request.headers.get("HX-Request") == "true":
                response = HttpResponse(status=204)
                response["HX-Redirect"] = success_url
                return response
            return redirect(success_url)
    else:
        form = UserEditForm(**kwargs)
    return render(request, "accounts/_user_edit_form.html", {"form": form, "akun": akun})


@login_required
def ganti_password_view(request):
    """Change the logged-in user's own password (open to every role)."""
    if request.method == "POST":
        form = GantiPasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # stay logged in
            messages.success(request, "Password berhasil diganti.")
            return redirect("accounts:ganti_password")
    else:
        form = GantiPasswordForm(request.user)
    for field in form.fields.values():
        field.widget.attrs["class"] = TEXT_INPUT_CLASSES
    return render(request, "accounts/ganti_password.html", {"form": form})


def _ke_tab_satuan(request, matra=""):
    """Back to the Satuan tab, on ``matra``'s sub-tab when given."""
    url = f"{reverse('accounts:pengaturan')}?tab=satuan"
    if matra in dict(roles.MATRA):
        url += f"&matra={matra}"
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


@login_required
def satuan_form_view(request, uid=None):
    """Tambah (uid=None) or Edit a Satuan in the Pengaturan modal."""
    satuan = get_object_or_404(Satuan, uuid=uid) if uid else None
    if request.method == "POST":
        form = SatuanForm(request.POST, instance=satuan)
        if form.is_valid():
            simpan = form.save()
            messages.success(request, f"Satuan {simpan.nama} berhasil disimpan.")
            return _ke_tab_satuan(request, simpan.matra)
    else:
        # Tambah Satuan on a matra's sub-tab starts on that matra.
        awal = {"matra": request.GET.get("matra")} if satuan is None and request.GET.get("matra") in dict(roles.MATRA) else None
        form = SatuanForm(instance=satuan, initial=awal)
    return render(request, "accounts/_satuan_form.html", {"form": form, "satuan": satuan})


@login_required
def satuan_delete(request, uid):
    """GET: confirmation for the modal. POST: delete the Satuan."""
    satuan = get_object_or_404(Satuan, uuid=uid)
    if request.method == "POST":
        if satuan.biodata.exists() or satuan.pemeriksaan_golongan_b.exists():
            messages.error(request, f"Satuan {satuan.nama} masih dipakai di biodata atau pemeriksaan, jadi tidak bisa dihapus.")
            return _ke_tab_satuan(request, satuan.matra)
        satuan.delete()
        messages.success(request, f"Satuan {satuan.nama} berhasil dihapus.")
        return _ke_tab_satuan(request, satuan.matra)
    return render(request, "accounts/_satuan_delete_confirm.html", {"satuan": satuan})
