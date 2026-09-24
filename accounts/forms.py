from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User

from fleet.models import Vehicle

from . import pemeriksaan as checklist
from . import roles
from .models import Laporan, PemeriksaanBermotor, PemeriksaanGolonganB

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

CHECKBOX_CLASSES = (
    "h-4 w-4 rounded border-slate-300 text-navy focus:ring-gold "
    "dark:border-slate-600 dark:bg-slate-900"
)


class LoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, initial=True, label="Ingat saya")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({
            "class": TEXT_INPUT_CLASSES,
            "placeholder": "Username",
            "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "class": TEXT_INPUT_CLASSES,
            "placeholder": "Password",
        })
        self.fields["remember_me"].widget.attrs.update({"class": CHECKBOX_CLASSES})


class UserCreateForm(forms.ModelForm):
    """New users get roles.DEFAULT_PASSWORD; no password is typed in the form."""

    keanggotaan = forms.ChoiceField(label="Keanggotaan", choices=roles.KEANGGOTAAN)

    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, allow_superuser=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Only a superuser may create another superuser.
        if not allow_superuser:
            self.fields["keanggotaan"].choices = [
                choice for choice in roles.KEANGGOTAAN if choice[0] != roles.SUPERUSER
            ]
        self.fields["keanggotaan"].choices = [("", "Pilih keanggotaan")] + list(self.fields["keanggotaan"].choices)
        self.fields["username"].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["keanggotaan"].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["username"].widget.attrs["placeholder"] = "teknisi2"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(roles.DEFAULT_PASSWORD)
        kode = self.cleaned_data["keanggotaan"]
        user.is_superuser = kode == roles.SUPERUSER
        # Superuser and Admin can open Django admin.
        user.is_staff = kode in (roles.SUPERUSER, roles.ADMIN)
        if commit:
            user.save()
            if kode != roles.SUPERUSER:
                user.groups.set([Group.objects.get(name=roles.GROUP_NAMES[kode])])
        return user


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
        self.fields["satuan"].widget.attrs["placeholder"] = "Satuan Kerja ABC"


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
            jumlah_raw = self.data.get(prefix + "jml", "").strip()
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
            items.append({
                "nomor": nomor,
                "nama_alat": nama,
                "jumlah": jumlah,
                "kondisi": kondisi,
                "foto": foto or None,
                "keterangan": self.data.get(prefix + "keterangan", "").strip(),
            })
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

    class Meta:
        model = PemeriksaanBermotor
        fields = [
            "vehicle", "bbm", "buku_harian", "macam_pemeriksaan", "tempat_pemeriksaan",
            "ukuran_ban", "ban_depan_kiri", "ban_depan_kanan", "ban_belakang_kiri", "ban_belakang_kanan", "ban_cadangan",
        ]
