from django import forms

from .images import compress_photo
from .models import Vehicle, VehiclePhoto

MIN_FOTO = 4
MAKS_FOTO = 4
# The sides the photos are of, in the order they are stored.
SISI_FOTO = ["Depan", "Belakang", "Kiri", "Kanan"]

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


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleImageInput(attrs={"accept": "image/*"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleImageField, self).clean(f, initial) for f in files]


class VehicleForm(forms.ModelForm):
    # On create: MIN_FOTO to MAKS_FOTO photos (all named "foto"). On edit:
    # one input per side (foto_1..foto_4); a side left empty keeps its photo.
    foto = MultipleImageField(required=False, label="Foto Kendaraan")

    class Meta:
        model = Vehicle
        fields = ["nopol", "merek", "no_chasis", "no_mesin", "kepemilikan"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = FILE_INPUT_CLASSES if name == "foto" else TEXT_INPUT_CLASSES
        self.fields["nopol"].widget.attrs["placeholder"] = "B 9021 XY"
        self.fields["merek"].widget.attrs["placeholder"] = "TOYOTA HILUX"
        # Organik or Pinjaman has to be picked: a new vehicle starts on the
        # empty option, an existing one on what it has.
        self.fields["kepemilikan"].choices = [("", "— Pilih status —"), *Vehicle.Kepemilikan.choices]
        if not self.instance.pk:
            self.initial["kepemilikan"] = ""
        # Typed and stored in capitals (see _clean_kapital).
        for name in self.KAPITAL:
            self.fields[name].widget.attrs["class"] += " uppercase"

    KAPITAL = ("nopol", "merek", "no_chasis", "no_mesin")

    def _clean_kapital(self, name):
        return (self.cleaned_data.get(name) or "").strip().upper()

    def clean_nopol(self):
        return self._clean_kapital("nopol")

    def clean_merek(self):
        return self._clean_kapital("merek")

    def clean_no_chasis(self):
        return self._clean_kapital("no_chasis")

    def clean_no_mesin(self):
        return self._clean_kapital("no_mesin")

    def sisi_foto(self):
        """Each side: its number (the foto_N input), label and current photo (or None)."""
        lama = list(self.instance.fotos.all()) if self.instance.pk else []
        return [
            {"nomor": i, "label": label, "foto": lama[i - 1] if i <= len(lama) else None}
            for i, label in enumerate(SISI_FOTO, 1)
        ]

    def clean_foto(self):
        files = self.cleaned_data["foto"]
        if self.instance.pk and not files:
            return files  # edit: the sides are checked in clean()
        if len(files) < MIN_FOTO:
            raise forms.ValidationError(f"Unggah minimal {MIN_FOTO} foto kendaraan (baru {len(files)}).")
        if len(files) > MAKS_FOTO:
            raise forms.ValidationError(f"Foto kendaraan maksimal {MAKS_FOTO} (terkirim {len(files)}).")
        return files

    def clean(self):
        cleaned = super().clean()
        self._foto_per_sisi = {}
        if self.instance.pk and not cleaned.get("foto"):
            lama = self.instance.fotos.count()
            for i, label in enumerate(SISI_FOTO, 1):
                f = self.files.get(f"foto_{i}")
                if f:
                    try:
                        self._foto_per_sisi[i] = forms.ImageField().clean(f)
                    except forms.ValidationError as e:
                        self.add_error("foto", f"Foto {label}: {e.messages[0]}")
            # A side without a photo yet can't be left empty.
            kurang = [label for i, label in enumerate(SISI_FOTO, 1) if i > lama and i not in self._foto_per_sisi]
            if kurang:
                self.add_error("foto", f"Lengkapi foto: {', '.join(kurang)}.")
        return cleaned

    def save(self, commit=True):
        vehicle = super().save(commit=commit)
        if commit and self._foto_per_sisi:
            lama = list(vehicle.fotos.all())
            for i, f in sorted(self._foto_per_sisi.items()):
                if i <= len(lama):
                    lama[i - 1].image.delete(save=False)
                    lama[i - 1].image = compress_photo(f)
                    lama[i - 1].save()
                else:
                    VehiclePhoto.objects.create(vehicle=vehicle, image=compress_photo(f))
        files = self.cleaned_data["foto"]
        if commit and files:
            for old in vehicle.fotos.all():
                old.image.delete(save=False)
            vehicle.fotos.all().delete()
            for f in files:
                VehiclePhoto.objects.create(vehicle=vehicle, image=compress_photo(f))
        return vehicle
