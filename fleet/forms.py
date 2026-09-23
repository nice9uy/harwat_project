from django import forms

from .images import compress_photo
from .models import Vehicle, VehiclePhoto

MIN_FOTO = 4

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
    # On create: at least MIN_FOTO photos. On edit: leave empty to keep the
    # current photos, or upload a new set (again at least MIN_FOTO) to
    # replace all of them.
    foto = MultipleImageField(required=False, label="Foto Kendaraan")

    class Meta:
        model = Vehicle
        fields = ["nopol", "merek", "odometer_km", "no_chasis", "no_mesin"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = FILE_INPUT_CLASSES if name == "foto" else TEXT_INPUT_CLASSES
        self.fields["nopol"].widget.attrs["placeholder"] = "B 9021 XY"
        self.fields["merek"].widget.attrs["placeholder"] = "Toyota Hilux"

    def clean_foto(self):
        files = self.cleaned_data["foto"]
        keeping_existing = not files and self.instance.pk and self.instance.fotos.count() >= MIN_FOTO
        if not keeping_existing and len(files) < MIN_FOTO:
            raise forms.ValidationError(f"Unggah minimal {MIN_FOTO} foto kendaraan (baru {len(files)}).")
        return files

    def save(self, commit=True):
        vehicle = super().save(commit=commit)
        files = self.cleaned_data["foto"]
        if commit and files:
            for old in vehicle.fotos.all():
                old.image.delete(save=False)
            vehicle.fotos.all().delete()
            for f in files:
                VehiclePhoto.objects.create(vehicle=vehicle, image=compress_photo(f))
        return vehicle
