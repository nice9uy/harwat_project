from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.validators import UnicodeUsernameValidator as UsernameValidator

from fleet.images import compress_photo
from fleet.models import Vehicle

from . import pemeriksaan as checklist
from . import roles
from .models import (
    MAKS_FOTO,
    AkunPublik,
    Anggota,
    BawahanPimpinan,
    Laporan,
    PemeriksaanBermotor,
    PemeriksaanDiesel,
    PemeriksaanJeepDiesel,
    PemeriksaanRansus,
    PemeriksaanRantis,
    PemeriksaanGolonganB,
    Satuan,
    VpnPeer,
)

TEXT_INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-gold "
    "focus:outline-none focus:ring-2 focus:ring-gold/40 "
    "dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 "
    "dark:placeholder:text-slate-500"
)

FILE_INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm file:mr-3 file:rounded-md file:border-0 "
    "file:bg-green-600 file:px-3 file:py-1.5 file:text-sm file:font-medium "
    "file:text-white hover:file:bg-green-700 "
    "dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
)


class LoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, initial=True, label="Ingat saya")
    # Django's own Indonesian text comes out as "nama pengguna nama pengguna".
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Nama pengguna atau kata sandi salah. Huruf besar/kecil berpengaruh.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # App input style, with room for the icons on the login page.
        field = TEXT_INPUT_CLASSES.replace("px-3 py-2", "py-2.5 pl-10 pr-10")
        self.fields["username"].widget.attrs.update({
            "class": field,
            "placeholder": "nama.pengguna",
            "autofocus": True,
            "autocomplete": "username",
        })
        self.fields["password"].widget.attrs.update({
            "class": field,
            "placeholder": "••••••••",
            "autocomplete": "current-password",
            ":type": "lihat ? 'text' : 'password'",
        })
        self.fields["remember_me"].widget.attrs.update({
            "class": "h-4 w-4 rounded border-slate-300 accent-navy focus:ring-gold dark:border-slate-600 dark:bg-slate-900",
        })

    def get_invalid_login_error(self):
        # A switched-off account (Nonaktifkan on the Anggota Tim page) is told
        # so, but only with its right password: a wrong one gets the usual
        # message, so the form doesn't reveal which usernames exist.
        user = User.objects.filter(username=self.cleaned_data.get("username")).first()
        if user is not None and not user.is_active and user.check_password(self.cleaned_data.get("password") or ""):
            if user.last_login is None:
                return forms.ValidationError(
                    "Akun Anda belum diaktifkan. Tunggu aktivasi dari Admin matra Anda.", code="inactive",
                )
            return forms.ValidationError(
                "Akun Anda dinonaktifkan. Hubungi Ketua Tim atau admin untuk mengaktifkannya kembali.",
                code="inactive",
            )
        return super().get_invalid_login_error()


def _siapkan_keanggotaan(form, kode_pengelola, kecuali=None, admin=None):
    """Set up the keanggotaan / ketua_tim fields shared by the user forms.

    ``kecuali`` is an Anggota node that may not be picked as Ketua Tim
    (the user being edited). ``kode_pengelola`` is the role of the user
    filling in the form: it limits the roles on offer (see roles.boleh_kelola).
    ``admin``: that user is this Admin, who only picks their own Ketua Tim.
    """
    ketua = Anggota.get_root_nodes().select_related("user").order_by("user__username")
    if admin is not None:
        ketua = ketua.filter(admin=admin)
    if kecuali is not None:
        ketua = ketua.exclude(pk=kecuali.pk)
    form.fields["ketua_tim"].queryset = ketua
    form.fields["ketua_tim"].label_from_instance = lambda node: node.user.username
    form.ada_ketua = ketua.exists()
    choices = [c for c in roles.KEANGGOTAAN if roles.boleh_kelola(kode_pengelola, c[0])]
    # Tim members go under a Ketua Tim, so they need one to exist first.
    if not form.ada_ketua:
        choices = [c for c in choices if c[0] not in roles.TIM]
    form.fields["keanggotaan"].choices = [("", "Pilih keanggotaan")] + list(choices)
    form.fields["keanggotaan"].widget.attrs.update({"class": TEXT_INPUT_CLASSES, "x-model": "keanggotaan"})
    form.fields["ketua_tim"].widget.attrs["class"] = TEXT_INPUT_CLASSES
    if "matra" in form.fields:
        form.fields["matra"].widget.attrs["class"] = TEXT_INPUT_CLASSES
    if "bawahan" in form.fields:
        form.fields["bawahan"].queryset = Anggota.get_root_nodes().select_related("user").order_by("user__username")
        form.fields["bawahan"].label_from_instance = lambda node: node.user.username
        form.fields["bawahan"].widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 accent-gold dark:border-slate-600 dark:bg-slate-900"


def _cek_ketua(form, cleaned):
    if cleaned.get("keanggotaan") in roles.TIM and not cleaned.get("ketua_tim"):
        form.add_error("ketua_tim", "Pilih Ketua Tim untuk anggota tim ini.")


def _cek_matra(form, cleaned):
    """An Admin, a Ketua Tim and a Tim member have a matra (roles.BERMATRA);
    nobody else does."""
    if cleaned.get("keanggotaan") in roles.BERMATRA and not cleaned.get("matra"):
        form.add_error("matra", "Pilih matra untuk user ini.")


def _cek_bawahan(form, cleaned):
    """A Pimpinan Tim is made with at least one Ketua Tim under them."""
    if cleaned.get("keanggotaan") == roles.PIMPINAN_TIM and not cleaned.get("bawahan"):
        form.add_error("bawahan", "Pilih minimal satu Ketua Tim untuk Pimpinan Ketua Tim ini.")


def simpan_bawahan(user, kode, ketua):
    """Keep exactly ``ketua`` (Anggota root nodes) under a Pimpinan Tim; for
    any other role terapkan_keanggotaan() has already dropped them."""
    if kode != roles.PIMPINAN_TIM:
        return
    BawahanPimpinan.objects.filter(pimpinan=user).exclude(ketua__in=ketua).delete()
    ada = set(BawahanPimpinan.objects.filter(pimpinan=user).values_list("ketua_id", flat=True))
    BawahanPimpinan.objects.bulk_create([BawahanPimpinan(pimpinan=user, ketua=n) for n in ketua if n.pk not in ada])


class _SatuanAkunMixin:
    """A Satuan for the account (AkunPublik.satuan): a typed field with
    suggestions (templates/_autocomplete.html), posting the unit's pk."""

    def _siapkan_satuan(self, awal=None):
        self.fields["satuan"] = forms.ModelChoiceField(
            label="Satuan", queryset=Satuan.objects.order_by("nama"), required=False, initial=awal,
        )

    @property
    def satuan_opsi(self):
        return [{"v": pk, "l": nama} for pk, nama in self.fields["satuan"].queryset.values_list("pk", "nama")]

    @property
    def satuan_nilai(self):
        """The pk shown in the field: what was posted, else the initial unit."""
        if self.is_bound:
            return self.data.get("satuan", "")
        awal = self.initial.get("satuan", self.fields["satuan"].initial)
        return getattr(awal, "pk", awal) or ""


def simpan_satuan(user, satuan):
    AkunPublik.objects.filter(user=user).update(satuan=satuan)


def simpan_matra(user, kode, matra):
    """Keep the matra on the user's AkunPublik for the roles that have one
    (roles.BERMATRA); clear it for any other role."""
    AkunPublik.objects.filter(user=user).update(matra=matra if kode in roles.BERMATRA else "")


def terapkan_keanggotaan(user, kode, ketua=None, admin=None):
    """Give a saved user the role ``kode``: flags, group, place in the Anggota
    tree and, for a Ketua Tim, the Admin ``admin`` above them (a Tim member
    made Ketua Tim without one keeps their old ketua's Admin)."""
    user.is_superuser = kode == roles.SUPERUSER
    # Superuser and Admins are staff (Django admin itself is superuser-only).
    user.is_staff = kode == roles.SUPERUSER or kode in roles.ADMIN
    user.save(update_fields=["is_superuser", "is_staff"])
    if kode == roles.SUPERUSER:
        user.groups.clear()
    else:
        user.groups.set([Group.objects.get(name=roles.GROUP_NAMES[kode])])

    if kode != roles.PIMPINAN_TIM:
        # The Ketua Tim a Pimpinan Tim picked go with the role.
        BawahanPimpinan.objects.filter(pimpinan=user).delete()

    node = Anggota.objects.filter(user=user).first()
    if kode == roles.KETUA_TIM:
        if node is not None and not node.is_root():
            if admin is None:
                admin = node.get_parent().admin
            node.delete()  # a member has no children, so nothing is lost
            node = None
        if node is None:
            Anggota.add_root(user=user, admin=admin)
        elif admin is not None and node.admin_id != admin.pk:
            node.admin = admin
            node.save(update_fields=["admin"])
    elif kode in roles.TIM:
        ketua = Anggota.objects.get(pk=ketua.pk)  # treebeard wants fresh nodes
        if node is None:
            ketua.add_child(user=user)
        elif node.is_root():
            node.delete()  # was a Ketua Tim without members (checked by the form)
            Anggota.objects.get(pk=ketua.pk).add_child(user=user)
        elif node.get_parent().pk != ketua.pk:
            node.move(ketua, pos="last-child")
    elif node is not None:
        node.delete()


class UbahTimForm(forms.Form):
    """Move a Tim member to another Tim role under the same Ketua Tim."""

    keanggotaan = forms.ChoiceField(
        label="Tim",
        choices=[c for c in roles.KEANGGOTAAN if c[0] in roles.TIM],
        widget=forms.Select(attrs={"class": TEXT_INPUT_CLASSES}),
    )


class UserCreateForm(_SatuanAkunMixin, forms.ModelForm):
    """New users get roles.DEFAULT_PASSWORD; no password is typed in the form."""

    keanggotaan = forms.ChoiceField(label="Keanggotaan", choices=roles.KEANGGOTAAN)
    ketua_tim = forms.ModelChoiceField(
        label="Ketua Tim", queryset=Anggota.objects.none(), required=False, empty_label="Pilih ketua tim",
    )
    matra = forms.ChoiceField(label="Matra", choices=[("", "Pilih matra"), *roles.MATRA], required=False)
    # For a Pimpinan Tim: the Ketua Tim under them (models.BawahanPimpinan).
    bawahan = forms.ModelMultipleChoiceField(
        label="Ketua Tim Bawahan", queryset=Anggota.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, kode_pengelola=None, ketua=None, admin=None, **kwargs):
        super().__init__(*args, **kwargs)
        _siapkan_keanggotaan(self, kode_pengelola)
        # Starts on the unit of whoever they are added under; it can be changed.
        di_bawah_satuan = admin if admin is not None else ketua.user if ketua is not None else None
        self._siapkan_satuan(getattr(getattr(di_bawah_satuan, "publik", None), "satuan", None))
        self.fields["username"].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["username"].widget.attrs["placeholder"] = "teknisi2"
        # "+ Anggota" adds Tim members on a Ketua Tim row and Ketua Tim on an
        # Admin row: there only that role, fixed under that user. Tim members
        # come only that way; so does Ketua Tim for an Admin, who only
        # manages Ketua Tim under them.
        self.ketua = ketua
        self.admin = admin
        # Starts on the matra of whoever they are added under; it can be changed.
        di_bawah = admin if admin is not None else ketua.user if ketua is not None else None
        if di_bawah is not None:
            self.fields["matra"].initial = getattr(getattr(di_bawah, "publik", None), "matra", "")
        # A Tim member added under a Ketua Tim serves in that Ketua Tim's matra:
        # no choice shown (clean_matra fills it in).
        self.matra_ketua = getattr(getattr(ketua.user, "publik", None), "matra", "") if ketua is not None else ""
        if self.matra_ketua:
            self.fields["matra"].widget = forms.HiddenInput()
        hanya = roles.KETUA_TIM if admin is not None else None
        if hanya is not None:
            self.fields["keanggotaan"].choices = [
                c for c in self.fields["keanggotaan"].choices if c[0] == hanya
            ]
            self.fields["keanggotaan"].initial = hanya
        elif ketua is None:
            lewat_tombol = set(roles.TIM)
            if kode_pengelola == roles.ADMIN_ROLE:
                lewat_tombol.add(roles.KETUA_TIM)
            self.fields["keanggotaan"].choices = [
                c for c in self.fields["keanggotaan"].choices if c[0] not in lewat_tombol
            ]
        else:
            self.fields["keanggotaan"].choices = [("", "Pilih keanggotaan")] + [
                c for c in roles.KEANGGOTAAN if c[0] in roles.TIM
            ]
            self.fields["ketua_tim"].initial = ketua.pk
            self.fields["ketua_tim"].widget = forms.HiddenInput()

    def clean_username(self):
        """Unique whatever the case ("Ketua" and "ketua" are the same name),
        as on the Daftar Ketua Tim form; see migration 0073 for the database side."""
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Nama pengguna ini sudah dipakai.")
        return username

    def clean_ketua_tim(self):
        ketua = self.cleaned_data.get("ketua_tim")
        return self.ketua if self.ketua is not None else ketua

    def clean_matra(self):
        return self.matra_ketua or self.cleaned_data.get("matra")

    def clean(self):
        cleaned = super().clean()
        _cek_ketua(self, cleaned)
        _cek_matra(self, cleaned)
        _cek_bawahan(self, cleaned)
        return cleaned

    def save(self, commit=True):
        from .vpn_utils import generate_keypair
        user = super().save(commit=False)
        user.set_password(roles.DEFAULT_PASSWORD)
        if commit:
            user.save()
            terapkan_keanggotaan(
                user, self.cleaned_data["keanggotaan"], self.cleaned_data["ketua_tim"],
                admin=self.admin,
            )
            simpan_matra(user, self.cleaned_data["keanggotaan"], self.cleaned_data.get("matra"))
            simpan_satuan(user, self.cleaned_data.get("satuan"))
            simpan_bawahan(user, self.cleaned_data["keanggotaan"], self.cleaned_data.get("bawahan"))
            priv, pub = generate_keypair()
            VpnPeer.objects.create(user=user, peer_name=user.username, private_key=priv, public_key=pub)
        return user


class UserEditForm(_SatuanAkunMixin, forms.Form):
    """Change an existing user's keanggotaan and, for Tim members, their Ketua Tim."""

    keanggotaan = forms.ChoiceField(label="Keanggotaan", choices=roles.KEANGGOTAAN)
    ketua_tim = forms.ModelChoiceField(
        label="Ketua Tim", queryset=Anggota.objects.none(), required=False, empty_label="Pilih ketua tim",
    )
    vpn_peer_name = forms.CharField(
        label="Nama Peer VPN", max_length=50, required=False,
        widget=forms.TextInput(attrs={"class": TEXT_INPUT_CLASSES, "placeholder": "peer1"}),
    )
    matra = forms.ChoiceField(label="Matra", choices=[("", "Pilih matra"), *roles.MATRA], required=False)
    # For a Pimpinan Tim: the Ketua Tim under them (models.BawahanPimpinan).
    bawahan = forms.ModelMultipleChoiceField(
        label="Ketua Tim Bawahan", queryset=Anggota.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user, kode_pengelola=None, admin=None, **kwargs):
        """``admin``: the editor is this Admin (see _siapkan_keanggotaan)."""
        self.user = user
        self.node = Anggota.objects.filter(user=user).first()
        parent = self.node.get_parent() if self.node is not None and not self.node.is_root() else None
        vpn = VpnPeer.objects.filter(user=user).first()
        kwargs.setdefault("initial", {
            "keanggotaan": roles.keanggotaan_kode(user) or "",
            "ketua_tim": parent.pk if parent else None,
            "vpn_peer_name": vpn.peer_name if vpn else "",
            "matra": getattr(getattr(user, "publik", None), "matra", ""),
            "bawahan": list(BawahanPimpinan.objects.filter(pimpinan=user).values_list("ketua_id", flat=True)),
        })
        super().__init__(*args, **kwargs)
        _siapkan_keanggotaan(self, kode_pengelola, kecuali=self.node, admin=admin)
        self._siapkan_satuan(getattr(getattr(user, "publik", None), "satuan", None))
        self.admin = admin
        kode_lama = roles.keanggotaan_kode(user)
        self.punya_ketua = kode_lama == roles.ADMIN_ROLE and Anggota.objects.filter(admin=user).exists()

    def clean(self):
        cleaned = super().clean()
        _cek_ketua(self, cleaned)
        kode = cleaned.get("keanggotaan")
        _cek_matra(self, cleaned)
        _cek_bawahan(self, cleaned)
        if self.punya_ketua and kode != roles.ADMIN_ROLE:
            self.add_error(
                "keanggotaan",
                "Admin ini masih punya Ketua Tim. Hapus Ketua Tim-nya dulu.",
            )
        if self.node is not None and self.node.get_children_count() and kode != roles.KETUA_TIM:
            self.add_error(
                "keanggotaan",
                "Ketua Tim ini masih punya anggota. Pindahkan anggotanya ke ketua lain dulu.",
            )
        return cleaned

    def save(self):
        terapkan_keanggotaan(
            self.user, self.cleaned_data["keanggotaan"], self.cleaned_data["ketua_tim"], admin=self.admin,
        )
        simpan_matra(self.user, self.cleaned_data["keanggotaan"], self.cleaned_data.get("matra"))
        simpan_satuan(self.user, self.cleaned_data.get("satuan"))
        simpan_bawahan(self.user, self.cleaned_data["keanggotaan"], self.cleaned_data.get("bawahan"))
        peer_name = self.cleaned_data.get("vpn_peer_name", "").strip()
        if peer_name:
            VpnPeer.objects.update_or_create(user=self.user, defaults={"peer_name": peer_name})
        else:
            VpnPeer.objects.filter(user=self.user).delete()
        return self.user


class VpnForm(forms.Form):
    peer_name = forms.CharField(
        label="Nama Peer", max_length=50, required=False,
        widget=forms.TextInput(attrs={"class": TEXT_INPUT_CLASSES, "placeholder": "peer1"}),
    )
    client_ip = forms.CharField(
        label="IP Client (CIDR)", max_length=50, required=False,
        widget=forms.TextInput(attrs={"class": TEXT_INPUT_CLASSES, "placeholder": "Kosongkan untuk otomatis"}),
    )
    preshared_key = forms.CharField(
        label="Preshared Key", required=False,
        widget=forms.TextInput(attrs={"class": TEXT_INPUT_CLASSES, "placeholder": "Kosongkan untuk generate otomatis"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_client_ip(self):
        import ipaddress
        from .vpn_utils import ip_server, subnet
        nilai = self.cleaned_data.get("client_ip", "").strip()
        if not nilai:
            return ""
        try:
            ip = ipaddress.ip_address(nilai.split("/")[0])
        except ValueError:
            raise forms.ValidationError("Alamat IP tidak valid.")
        if ip not in subnet() or ip == ip_server() or ip in (subnet().network_address, subnet().broadcast_address):
            raise forms.ValidationError(f"IP harus di dalam subnet VPN {subnet()} dan bukan alamat server.")
        nilai = f"{ip}/32"
        if VpnPeer.objects.filter(client_ip=nilai).exclude(user=self.user).exists():
            raise forms.ValidationError("IP ini sudah dipakai peer lain.")
        return nilai

    def save(self, user):
        from .vpn_utils import generate_keypair, ip_bebas
        peer_name = self.cleaned_data.get("peer_name", "").strip()
        client_ip = self.cleaned_data.get("client_ip", "").strip()
        preshared_key = self.cleaned_data.get("preshared_key", "").strip()
        if peer_name:
            vpn = VpnPeer.objects.filter(user=user).first()
            # Generate keypair only if not already generated
            if vpn and vpn.private_key:
                priv, pub = vpn.private_key, vpn.public_key
            else:
                priv, pub = generate_keypair()
            client_ip = client_ip or (vpn.client_ip if vpn else "") or ip_bebas()
            VpnPeer.objects.update_or_create(user=user, defaults={
                "peer_name": peer_name,
                "private_key": priv, "public_key": pub,
                "client_ip": client_ip, "preshared_key": preshared_key,
            })
        else:
            VpnPeer.objects.filter(user=user).delete()


class BiodataForm(forms.ModelForm):
    """The shared BIODATA tab (stored as a Laporan / Biodata Pemeriksa row)."""

    class Meta:
        model = Laporan
        fields = ["tipe_identitas", "nip", "nama", "pangkat", "jabatan", "satuan", "foto"]
        widgets = {
            "foto": forms.FileInput(attrs={
                "accept": "image/*",
                "capture": "environment",
                "@change": "fotoPreview = $event.target.files[0] ? URL.createObjectURL($event.target.files[0]) : null",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = FILE_INPUT_CLASSES if name == "foto" else TEXT_INPUT_CLASSES
        # TNI only: the PNS choice is gone, whatever an older biodata holds.
        self.fields["tipe_identitas"].choices = [(Laporan.TipeIdentitas.TNI, "TNI")]
        self.fields["tipe_identitas"].required = False
        self.fields["nip"].label = "NRP"
        self.fields["nip"].widget.attrs["placeholder"] = "21990123456789"
        self.fields["nama"].widget.attrs["placeholder"] = "BUDI SANTOSO"
        self.fields["pangkat"].widget.attrs["placeholder"] = "KAPTEN"
        self.fields["jabatan"].widget.attrs["placeholder"] = "TEKNISI"
        # Typed and stored in capitals (see _clean_kapital).
        for name in self.KAPITAL:
            self.fields[name].widget.attrs["class"] += " uppercase"
        # Satuan comes from the Satuan table (Pengaturan > Satuan).
        self.fields["satuan"].queryset = Satuan.objects.order_by("nama")

    def clean_tipe_identitas(self):
        return Laporan.TipeIdentitas.TNI

    KAPITAL = ("nip", "nama", "pangkat", "jabatan")

    def _clean_kapital(self, name):
        return (self.cleaned_data.get(name) or "").strip().upper()

    def clean_nip(self):
        return self._clean_kapital("nip")

    def clean_nama(self):
        return self._clean_kapital("nama")

    def clean_pangkat(self):
        return self._clean_kapital("pangkat")

    def clean_jabatan(self):
        return self._clean_kapital("jabatan")

    @property
    def satuan_opsi(self):
        """Satuan choices for the autocomplete field."""
        return [{"v": s.pk, "l": s.nama} for s in self.fields["satuan"].queryset]


class LaporanForm(BiodataForm):
    captcha = forms.CharField(label="Kode Keamanan", max_length=10)

    def __init__(self, *args, expected_captcha="", **kwargs):
        super().__init__(*args, **kwargs)
        self._expected_captcha = expected_captcha
        self.fields["captcha"].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["captcha"].widget.attrs["placeholder"] = "Ketik kode di atas"
        self.fields["captcha"].widget.attrs["autocomplete"] = "off"

    def clean_captcha(self):
        value = self.cleaned_data["captcha"].strip().upper()
        if not self._expected_captcha or value != self._expected_captcha:
            raise forms.ValidationError("Kode keamanan tidak sesuai.")
        return value


def clean_foto(files, nama, label, errors):
    """The photos posted under ``nama`` (several inputs share it): at most
    MAKS_FOTO valid images. Problems go to ``errors`` using ``label``."""
    daftar = [f for f in files.getlist(nama) if f]
    if len(daftar) > MAKS_FOTO:
        errors.append(f"Foto {label} maksimal {MAKS_FOTO} (terkirim {len(daftar)}).")
        return []
    bersih = []
    for f in daftar:
        try:
            bersih.append(forms.ImageField().clean(f))
        except forms.ValidationError:
            errors.append(f"Foto {label} bukan gambar yang valid.")
    return bersih


# Conditions that need proof: a part marked with one of these has a photo or
# a note, on every inspection form.
KONDISI_WAJIB_BUKTI = {"RR": "Rusak Ringan", "RB": "Rusak Berat", "TA": "Tidak Ada"}


class _ChecklistForm(forms.ModelForm):
    """Tab PEMERIKSAAN: scanned vehicle, header fields and the checklist.

    Checklist fields come from the accordion as alat_<n>_jml / _kondisi /
    _foto / _keterangan for each numbered part in ``alat`` and are
    validated into ``cleaned_items``. Subclasses set ``golongan``
    (Vehicle.group_kendaraan), ``alat`` and ``kondisi``.
    """

    golongan = None
    alat = []
    kondisi = []
    pakai_jumlah = True

    def clean_item_extra(self, prefix, label, errors):
        """Extra per-part fields of this group's form (none by default)."""
        return {}

    @property
    def daftar_galat(self):
        """The form's errors as lines for the page, each header field's
        prefixed with its name ("BBM: ...")."""
        baris = []
        for nama, galat in self.errors.items():
            label = self.fields[nama].label if nama in self.fields else ""
            baris += [f"{label}: {g}" if label else g for g in galat]
        return baris

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A photo is renamed (and shortened) when compressed, so its own
        # file name may be any length.
        if "foto_km" in self.fields:
            self.fields["foto_km"].max_length = None
        self.fields["vehicle"].queryset = Vehicle.objects.filter(group_kendaraan=self.golongan)
        # The page posts the vehicle's public uuid, never its pk.
        self.fields["vehicle"].to_field_name = "uuid"
        self.fields["vehicle"].error_messages["required"] = "Scan QR Code kendaraan terlebih dahulu."
        self.cleaned_items = []

    def clean(self):
        cleaned = super().clean()
        kondisi_valid = {kode for kode, _ in self.kondisi}
        items, errors = [], []
        for nomor, nama in self.alat:
            prefix = f"alat_{nomor}_"
            kondisi = self.data.get(prefix + "kondisi", "")
            if kondisi not in kondisi_valid:
                errors.append(f"Kondisi {nomor}. {nama} belum dipilih.")
            jumlah_raw = self.data.get(prefix + "jml", "").strip() if self.pakai_jumlah else ""
            jumlah = None
            if jumlah_raw:
                if not jumlah_raw.isdigit():
                    errors.append(f"Jumlah {nomor}. {nama} harus angka 0 atau lebih.")
                else:
                    jumlah = int(jumlah_raw)
            fotos = clean_foto(self.files, prefix + "foto", f"{nomor}. {nama}", errors)
            keterangan = self.data.get(prefix + "keterangan", "").strip()
            if kondisi in KONDISI_WAJIB_BUKTI and not fotos and not keterangan:
                errors.append(
                    f"{nomor}. {nama} ({KONDISI_WAJIB_BUKTI[kondisi]}): sertakan foto atau keterangan."
                )
            item = {
                "nomor": nomor,
                "nama_alat": nama,
                "kondisi": kondisi,
                "fotos": fotos,
                "keterangan": keterangan,
            }
            if self.pakai_jumlah:
                item["jumlah"] = jumlah
            item.update(self.clean_item_extra(prefix, f"{nomor}. {nama}", errors))
            items.append(item)
        if errors:
            raise forms.ValidationError(errors)
        self.cleaned_items = items
        return cleaned


class PemeriksaanGolonganBForm(_ChecklistForm):
    golongan = Vehicle.GroupKendaraan.GOLONGAN_B
    alat = checklist.ALAT_BERNOMOR
    kondisi = checklist.KONDISI

    class Meta:
        model = PemeriksaanGolonganB
        fields = [
            "vehicle", "pembagian_kelas", "eselon_reparasi", "macam_pemeriksaan",
            "km_kendaraan", "foto_km", "kesatuan",
            *PemeriksaanGolonganB.BAN_FIELDS, "kesimpulan", "keterangan",
        ]

    def save(self, commit=True):
        hasil = super().save(commit=False)
        # The odometer photo is shrunk like every other upload.
        if self.files.get("foto_km"):
            hasil.foto_km = compress_photo(self.files["foto_km"])
        if commit:
            hasil.save()
        return hasil


class PemeriksaanBermotorForm(_ChecklistForm):
    golongan = Vehicle.GroupKendaraan.KENDARAAN_BERMOTOR
    alat = checklist.KOMPONEN_BERMOTOR_BERNOMOR
    kondisi = checklist.KONDISI_BERMOTOR
    pakai_jumlah = False

    def save(self, commit=True):
        hasil = super().save(commit=False)
        # The odometer photo is shrunk like every other upload.
        if self.files.get("foto_km"):
            hasil.foto_km = compress_photo(self.files["foto_km"])
        if commit:
            hasil.save()
        return hasil

    class Meta:
        model = PemeriksaanBermotor
        fields = [
            "vehicle", "bbm", "km_kendaraan", "foto_km", "buku_harian", "macam_pemeriksaan", "tempat_pemeriksaan",
            "ukuran_ban", "ban_depan_kiri", "ban_depan_kanan", "ban_belakang_kiri", "ban_belakang_kanan", "ban_cadangan",
            "kesimpulan", "keterangan",
        ]


class PemeriksaanDieselForm(_ChecklistForm):
    golongan = Vehicle.GroupKendaraan.KENDARAAN_DIESEL
    alat = checklist.KOMPONEN_DIESEL_BERNOMOR
    kondisi = checklist.KONDISI_DIESEL
    pakai_jumlah = False

    class Meta:
        model = PemeriksaanDiesel
        fields = [
            "vehicle", "km_mil", "foto_km", "km_berfungsi", "jam_mesin", "jam_mesin_berfungsi",
            "buku_pemeliharaan", "kondisi_ranmor", "macam_pemeriksaan", "kesimpulan", "keterangan",
        ]

    def save(self, commit=True):
        hasil = super().save(commit=False)
        # The odometer photo is shrunk like every other upload.
        if self.files.get("foto_km"):
            hasil.foto_km = compress_photo(self.files["foto_km"])
        if commit:
            hasil.save()
        return hasil

    def clean_item_extra(self, prefix, label, errors):
        """Sat, Jumlah Riil and Jumlah Nyata columns of the diesel form."""
        extra = {"satuan": self.data.get(prefix + "sat", "").strip()[:30]}
        for field, kolom in (("jumlah_riil", "riil"), ("jumlah_nyata", "nyata")):
            raw = self.data.get(prefix + kolom, "").strip()
            if raw and not raw.isdigit():
                errors.append(f"Jumlah {kolom} {label} harus angka 0 atau lebih.")
            extra[field] = int(raw) if raw.isdigit() else None
        return extra


class PemeriksaanJeepDieselForm(PemeriksaanDieselForm):
    """Same fields and columns as Kendaraan Diesel, with the Jeep Diesel parts."""

    golongan = Vehicle.GroupKendaraan.JEEP_DIESEL
    alat = checklist.KOMPONEN_JEEP_DIESEL_BERNOMOR
    kondisi = checklist.KONDISI_JEEP_DIESEL

    class Meta(PemeriksaanDieselForm.Meta):
        model = PemeriksaanJeepDiesel


class PemeriksaanRantisForm(PemeriksaanDieselForm):
    """Same fields and columns as Kendaraan Diesel, with the RANTIS parts."""

    golongan = Vehicle.GroupKendaraan.RANTIS
    alat = checklist.KOMPONEN_RANTIS_BERNOMOR
    kondisi = checklist.KONDISI_RANTIS

    class Meta(PemeriksaanDieselForm.Meta):
        model = PemeriksaanRantis


class PemeriksaanRansusForm(PemeriksaanDieselForm):
    """Same fields and columns as Kendaraan Diesel, with the RANSUS equipment."""

    golongan = Vehicle.GroupKendaraan.RANSUS
    alat = checklist.KOMPONEN_RANSUS_BERNOMOR
    kondisi = checklist.KONDISI_RANSUS

    class Meta(PemeriksaanDieselForm.Meta):
        model = PemeriksaanRansus


class SatuanForm(forms.ModelForm):
    class Meta:
        model = Satuan
        fields = ["nama", "matra", "keterangan"]
        widgets = {"keterangan": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["nama"].widget.attrs["placeholder"] = "Yonif Mekanis 202/TM"
        # Starts on the tab the form was opened from; left out, it stays as it is.
        self.fields["matra"].required = False

    def clean_matra(self):
        return self.cleaned_data.get("matra") or self.instance.matra or "darat"


class GantiPasswordForm(PasswordChangeForm):
    """Ganti Password takes any new password: the AUTH_PASSWORD_VALIDATORS
    rules (length, numeric-only, common, like the username) aren't applied.
    The old password and the confirmation are still checked."""

    def validate_password_for_user(self, *args, **kwargs):
        pass

    def clean_new_password1(self):
        baru = self.cleaned_data.get("new_password1")
        if baru is not None and not baru.strip():
            raise forms.ValidationError("Password tidak boleh hanya berisi spasi.")
        if baru == roles.DEFAULT_PASSWORD:
            raise forms.ValidationError("Password baru tidak boleh sama dengan password bawaan.")
        return baru


class DaftarKetuaForm(forms.Form):
    """The account half of Daftar sebagai Ketua Tim on the login page (the
    biodata half is a BiodataForm). The password starts filled in with
    roles.DEFAULT_PASSWORD; any other will do too."""

    username = forms.CharField(label="Nama pengguna", max_length=150)
    password1 = forms.CharField(
        label="Kata sandi", strip=False, initial=roles.DEFAULT_PASSWORD,
        widget=forms.PasswordInput(render_value=True),
        help_text=f"Bawaan {roles.DEFAULT_PASSWORD}, boleh diganti.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["username"].widget.attrs.update({"placeholder": "nama.pengguna", "autocomplete": "username"})
        # Shown or hidden with the eye button (templates/accounts/_daftar_form.html).
        self.fields["password1"].widget.attrs.update({
            "autocomplete": "new-password", ":type": "lihat ? 'text' : 'password'",
            "class": TEXT_INPUT_CLASSES.replace("px-3", "pl-3 pr-10"),
        })

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        UsernameValidator()(username)
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Nama pengguna ini sudah dipakai.")
        return username

    def clean_password1(self):
        sandi = self.cleaned_data["password1"]
        if not sandi.strip():
            raise forms.ValidationError("Kata sandi tidak boleh hanya berisi spasi.")
        return sandi
