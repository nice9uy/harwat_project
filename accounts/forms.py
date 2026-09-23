from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Laporan

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
    "file:bg-navy file:px-3 file:py-1.5 file:text-sm file:font-medium "
    "file:text-white hover:file:bg-navy-light "
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


class UserCreateForm(UserCreationForm):
    email = forms.EmailField(required=False, label="Email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "email", "password1", "password2"):
            self.fields[name].widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["username"].widget.attrs["placeholder"] = "teknisi2"


class LaporanForm(forms.ModelForm):
    class Meta:
        model = Laporan
        fields = ["nip", "nama", "pangkat", "jabatan", "satuan", "foto"]
        widgets = {
            "foto": forms.FileInput(attrs={"accept": "image/*", "capture": "environment"}),
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
