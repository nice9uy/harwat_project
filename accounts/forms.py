from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User

from fleet.models import Vehicle

from . import pemeriksaan as checklist
from . import roles
from .models import Anggota, Laporan, PemeriksaanBermotor, PemeriksaanDiesel, PemeriksaanGolonganB, Satuan

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dark fields with room for the icon on the left (login page design).
        field = (
            "w-full rounded-lg border border-white/10 bg-black/60 py-3 pl-11 pr-11 text-base text-white "
            "placeholder:text-slate-400 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
        )
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
            "class": "h-5 w-5 rounded border-white/20 bg-black/60 accent-sky-500 focus:ring-sky-400",
        })


def _siapkan_keanggotaan(form, allow_superuser, kecuali=None):
    """Set up the keanggotaan / ketua_tim fields shared by the user forms.

    ``kecuali`` is an Anggota node that may not be picked as Ketua Tim
    (the user being edited).
    """
    ketua = Anggota.get_root_nodes().select_related("user").order_by("user__username")
    if kecuali is not None:
        ketua = ketua.exclude(pk=kecuali.pk)
    form.fields["ketua_tim"].queryset = ketua
    form.fields["ketua_tim"].label_from_instance = lambda node: node.user.username
    form.ada_ketua = ketua.exists()
    choices = roles.KEANGGOTAAN
    # Only a superuser may make someone a superuser.
    if not allow_superuser:
        choices = [c for c in choices if c[0] != roles.SUPERUSER]
    # Tim members go under a Ketua Tim, so they need one to exist first.
    if not form.ada_ketua:
        choices = [c for c in choices if c[0] not in roles.TIM]
    form.fields["keanggotaan"].choices = [("", "Pilih keanggotaan")] + list(choices)
    form.fields["keanggotaan"].widget.attrs.update({"class": TEXT_INPUT_CLASSES, "x-model": "keanggotaan"})
    form.fields["ketua_tim"].widget.attrs["class"] = TEXT_INPUT_CLASSES


def _cek_ketua(form, cleaned):
    if cleaned.get("keanggotaan") in roles.TIM and not cleaned.get("ketua_tim"):
        form.add_error("ketua_tim", "Pilih Ketua Tim untuk anggota tim ini.")


def terapkan_keanggotaan(user, kode, ketua=None):
    """Give a saved user the role ``kode``: flags, group and place in the Anggota tree."""
    user.is_superuser = kode == roles.SUPERUSER
    # Superuser and Admin can open Django admin.
    user.is_staff = kode in (roles.SUPERUSER, roles.ADMIN)
    user.save(update_fields=["is_superuser", "is_staff"])
    if kode == roles.SUPERUSER:
        user.groups.clear()
    else:
        user.groups.set([Group.objects.get(name=roles.GROUP_NAMES[kode])])

    node = Anggota.objects.filter(user=user).first()
    if kode == roles.KETUA_TIM:
        if node is not None and not node.is_root():
            node.delete()  # a member has no children, so nothing is lost
            node = None
        if node is None:
            Anggota.add_root(user=user)
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


class UserCreateForm(forms.ModelForm):
    """New users get roles.DEFAULT_PASSWORD; no password is typed in the form."""

    keanggotaan = forms.ChoiceField(label="Keanggotaan", choices=roles.KEANGGOTAAN)
    ketua_tim = forms.ModelChoiceField(
        label="Ketua Tim", queryset=Anggota.objects.none(), required=False, empty_label="Pilih ketua tim",
    )

    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, allow_superuser=False, ketua=None, **kwargs):
        super().__init__(*args, **kwargs)
        _siapkan_keanggotaan(self, allow_superuser)
        self.fields["username"].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["username"].widget.attrs["placeholder"] = "teknisi2"
        # Tim members are only added through "+ Anggota" on a Ketua Tim row:
        # there only Tim roles, fixed under that ketua; elsewhere no Tim roles.
        self.ketua = ketua
        if ketua is None:
            self.fields["keanggotaan"].choices = [
                c for c in self.fields["keanggotaan"].choices if c[0] not in roles.TIM
            ]
        else:
            self.fields["keanggotaan"].choices = [("", "Pilih keanggotaan")] + [
                c for c in roles.KEANGGOTAAN if c[0] in roles.TIM
            ]
            self.fields["ketua_tim"].initial = ketua.pk
            self.fields["ketua_tim"].widget = forms.HiddenInput()

    def clean_ketua_tim(self):
        ketua = self.cleaned_data.get("ketua_tim")
        return self.ketua if self.ketua is not None else ketua

    def clean(self):
        cleaned = super().clean()
        _cek_ketua(self, cleaned)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(roles.DEFAULT_PASSWORD)
        if commit:
            user.save()
            terapkan_keanggotaan(user, self.cleaned_data["keanggotaan"], self.cleaned_data["ketua_tim"])
        return user


class UserEditForm(forms.Form):
    """Change an existing user's keanggotaan and, for Tim members, their Ketua Tim."""

    keanggotaan = forms.ChoiceField(label="Keanggotaan", choices=roles.KEANGGOTAAN)
    ketua_tim = forms.ModelChoiceField(
        label="Ketua Tim", queryset=Anggota.objects.none(), required=False, empty_label="Pilih ketua tim",
    )

    def __init__(self, *args, user, allow_superuser=False, **kwargs):
        self.user = user
        self.node = Anggota.objects.filter(user=user).first()
        parent = self.node.get_parent() if self.node is not None and not self.node.is_root() else None
        kwargs.setdefault("initial", {
            "keanggotaan": roles.keanggotaan_kode(user) or "",
            "ketua_tim": parent.pk if parent else None,
        })
        super().__init__(*args, **kwargs)
        _siapkan_keanggotaan(self, allow_superuser, kecuali=self.node)

    def clean(self):
        cleaned = super().clean()
        _cek_ketua(self, cleaned)
        kode = cleaned.get("keanggotaan")
        if self.node is not None and self.node.get_children_count() and kode != roles.KETUA_TIM:
            self.add_error(
                "keanggotaan",
                "Ketua Tim ini masih punya anggota. Pindahkan anggotanya ke ketua lain dulu.",
            )
        return cleaned

    def save(self):
        terapkan_keanggotaan(self.user, self.cleaned_data["keanggotaan"], self.cleaned_data["ketua_tim"])
        return self.user


class BiodataForm(forms.ModelForm):
    """The shared BIODATA tab (stored as a Laporan / Biodata Pemeriksa row)."""

    class Meta:
        model = Laporan
        fields = ["nip", "nama", "pangkat", "jabatan", "satuan", "foto"]
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
        self.fields["nip"].label = "NIP/NRP"
        self.fields["nip"].widget.attrs["placeholder"] = "199001012015031001 (PNS) / 21990123456789 (TNI)"
        self.fields["nama"].widget.attrs["placeholder"] = "Budi Santoso"
        self.fields["pangkat"].widget.attrs["placeholder"] = "Kapten (TNI) / Penata Muda - III-a (PNS)"
        self.fields["jabatan"].widget.attrs["placeholder"] = "Teknisi"
        # Satuan comes from the Satuan table (Pengaturan > Satuan).
        self.fields["satuan"].empty_label = "Pilih satuan"
        self.fields["satuan"].queryset = Satuan.objects.order_by("nama")


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].queryset = Vehicle.objects.filter(group_kendaraan=self.golongan)
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
            foto = self.files.get(prefix + "foto")
            if foto:
                try:
                    foto = forms.ImageField().clean(foto)
                except forms.ValidationError:
                    errors.append(f"Foto {nomor}. {nama} bukan gambar yang valid.")
            item = {
                "nomor": nomor,
                "nama_alat": nama,
                "kondisi": kondisi,
                "foto": foto or None,
                "keterangan": self.data.get(prefix + "keterangan", "").strip(),
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
        fields = ["vehicle", "pembagian_kelas", "eselon_reparasi", "macam_pemeriksaan", "buku_jalan", "kesatuan"]


class PemeriksaanBermotorForm(_ChecklistForm):
    golongan = Vehicle.GroupKendaraan.KENDARAAN_BERMOTOR
    alat = checklist.KOMPONEN_BERMOTOR_BERNOMOR
    kondisi = checklist.KONDISI_BERMOTOR
    pakai_jumlah = False

    class Meta:
        model = PemeriksaanBermotor
        fields = [
            "vehicle", "bbm", "buku_harian", "macam_pemeriksaan", "tempat_pemeriksaan",
            "ukuran_ban", "ban_depan_kiri", "ban_depan_kanan", "ban_belakang_kiri", "ban_belakang_kanan", "ban_cadangan",
        ]


class PemeriksaanDieselForm(_ChecklistForm):
    golongan = Vehicle.GroupKendaraan.KENDARAAN_DIESEL
    alat = checklist.KOMPONEN_DIESEL_BERNOMOR
    kondisi = checklist.KONDISI_DIESEL
    pakai_jumlah = False

    class Meta:
        model = PemeriksaanDiesel
        fields = [
            "vehicle", "km_mil", "km_berfungsi", "jam_mesin", "jam_mesin_berfungsi",
            "buku_pemeliharaan", "kondisi_ranmor", "macam_pemeriksaan",
        ]

    def clean_item_extra(self, prefix, label, errors):
        """Sat, Jumlah Riil and Jumlah Nyata columns of the diesel form."""
        extra = {"satuan": self.data.get(prefix + "sat", "").strip()[:30]}
        for field, kolom in (("jumlah_riil", "riil"), ("jumlah_nyata", "nyata")):
            raw = self.data.get(prefix + kolom, "").strip()
            if raw and not raw.isdigit():
                errors.append(f"Jumlah {kolom} {label} harus angka 0 atau lebih.")
            extra[field] = int(raw) if raw.isdigit() else None
        return extra


class SatuanForm(forms.ModelForm):
    class Meta:
        model = Satuan
        fields = ["nama", "keterangan"]
        widgets = {"keterangan": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["nama"].widget.attrs["placeholder"] = "Yonif Mekanis 202/TM"
