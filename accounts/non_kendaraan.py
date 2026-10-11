"""Non Kendaraan menu: the inventory items that aren't vehicles."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from fleet.images import compress_photo
from fleet.models import NonKendaraan

from .forms import FILE_INPUT_CLASSES, TEXT_INPUT_CLASSES
from .paging import halaman


SEMUA_KOLOM = ["kode_barang", "nama_barang", "merek", "no_seri", "jumlah", "satuan", "kondisi", "foto"]
# The fields a group's form asks for and its table shows; a group not listed
# here has them all.
KOLOM = {
    NonKendaraan.Group.TENDA: ["nama_barang", "merek", "no_seri", "foto"],
}


def kolom(group):
    return KOLOM.get(group, SEMUA_KOLOM)


class NonKendaraanForm(forms.ModelForm):
    class Meta:
        model = NonKendaraan
        fields = SEMUA_KOLOM
        widgets = {"foto": forms.FileInput(attrs={"accept": "image/*"})}

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        for nama in set(self.fields) - set(kolom(group)):
            del self.fields[nama]
        for nama, field in self.fields.items():
            field.widget.attrs["class"] = FILE_INPUT_CLASSES if nama == "foto" else TEXT_INPUT_CLASSES
        if "kode_barang" in self.fields:
            # Asked for wherever it is shown; only groups without it leave it empty.
            self.fields["kode_barang"].required = True
            self.fields["kode_barang"].widget.attrs["placeholder"] = "BRG-0001"
        self.fields["nama_barang"].widget.attrs["placeholder"] = "Tenda Peleton"
        # The photo is renamed (and shortened) when compressed.
        self.fields["foto"].max_length = None
        if "satuan" in self.fields:
            self.fields["satuan"].widget.attrs["placeholder"] = "unit / buah / set"
        if "jumlah" in self.fields:
            self.fields["jumlah"].widget.attrs["min"] = 0

    def save(self, commit=True):
        barang = super().save(commit=False)
        # A newly picked photo is shrunk like every other upload.
        if self.files.get("foto"):
            barang.foto = compress_photo(self.files["foto"])
        if commit:
            barang.save()
        return barang


def _group(request):
    """Which tab the request belongs to (?group=tenda); unknown or missing
    values fall back to the first tab."""
    group = request.GET.get("group", "")
    return group if group in NonKendaraan.Group.values else NonKendaraan.Group.values[0]


def _list_url(group):
    """The page on the given group's tab (the first tab needs no query)."""
    url = reverse("accounts:non_kendaraan")
    return url if group == NonKendaraan.Group.values[0] else f"{url}?group={group}"


def _kembali(request, group):
    url = _list_url(group)
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


@login_required
def non_kendaraan_view(request):
    """One tab per group; its table, searched with ?q= (Kode Barang, Nama
    Barang, Merk/Type, No. Seri)."""
    cari = request.GET.get("q", "").strip()
    group = _group(request)
    daftar = NonKendaraan.objects.filter(group=group)
    if cari:
        daftar = daftar.filter(
            Q(kode_barang__icontains=cari) | Q(nama_barang__icontains=cari)
            | Q(merek__icontains=cari) | Q(no_seri__icontains=cari)
        )
    return render(request, "accounts/non_kendaraan.html", {
        "barang_list": halaman(request, daftar), "cari": cari, "group": group,
        "group_label": NonKendaraan.Group(group).label, "groups": NonKendaraan.Group.choices,
        "kolom": kolom(group),
    })


@login_required
def non_kendaraan_form(request, uid=None):
    """Tambah (uid=None, into the ?group= tab) or Edit an item in the page's modal."""
    barang = get_object_or_404(NonKendaraan, uuid=uid) if uid else None
    group = barang.group if barang else _group(request)
    if request.method == "POST":
        form = NonKendaraanForm(request.POST, request.FILES, instance=barang, group=group)
        if form.is_valid():
            simpan = form.save(commit=False)
            if barang is None:
                simpan.group = group
                simpan.ditambahkan_oleh = request.user
            simpan.save()
            messages.success(request, f"{simpan} berhasil disimpan.")
            return _kembali(request, group)
    else:
        form = NonKendaraanForm(instance=barang, group=group)
    return render(request, "accounts/_non_kendaraan_form.html", {
        "form": form, "barang": barang, "group": group, "group_label": NonKendaraan.Group(group).label,
    })


@login_required
def non_kendaraan_delete(request, uid):
    """GET: confirmation for the modal. POST: delete the item."""
    barang = get_object_or_404(NonKendaraan, uuid=uid)
    if request.method == "POST":
        barang.delete()
        messages.success(request, f"{barang} berhasil dihapus.")
        return _kembali(request, barang.group)
    return render(request, "accounts/_non_kendaraan_delete_confirm.html", {"barang": barang})
