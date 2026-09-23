from django import forms

from .models import Vehicle

TEXT_INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-gold "
    "focus:outline-none focus:ring-2 focus:ring-gold/40 "
    "dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 "
    "dark:placeholder:text-slate-500"
)


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["nopol", "merek", "odometer_km", "no_chasis", "no_mesin"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = TEXT_INPUT_CLASSES
        self.fields["nopol"].widget.attrs["placeholder"] = "B 9021 XY"
        self.fields["merek"].widget.attrs["placeholder"] = "Toyota Hilux"
