from django.db import migrations, models

MEMUASKAN = [("memuaskan", "Memuaskan"), ("kurang", "Kurang"), ("tidak", "Tidak")]
BAIK_SEDANG_BURUK = [("baik", "Baik"), ("sedang", "Sedang"), ("buruk", "Buruk")]
PENYEBAB = [("kekusutan", "Kekusutan"), ("tabrakan", "Tabrakan"), ("kesalahan_pakai", "Kesalahan pakai")]


def _kolom(name, choices, verbose_name, wajib):
    # Inspections saved before this migration have no conclusions; they get "".
    return migrations.AddField(
        model_name="pemeriksaangolonganb",
        name=name,
        field=models.CharField(
            choices=choices, max_length=20, verbose_name=verbose_name, default="",
            **({} if wajib else {"blank": True}),
        ),
        preserve_default=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_keadaan_ban_golongan_b"),
    ]

    operations = [
        _kolom("kegiatan_pemeriksaan", MEMUASKAN, "Kegiatan Pemeriksaan", True),
        _kolom("pemakaian_tehnis", BAIK_SEDANG_BURUK, "Pemakaian Tehnis", True),
        _kolom("pendapat_umum", MEMUASKAN, "Pendapat Umum", True),
        _kolom("kegiatan_ditpal", MEMUASKAN, "Kegiatan Ditpal", True),
        _kolom("pemeliharaan", BAIK_SEDANG_BURUK, "Pemeliharaan", True),
        _kolom("kerusakan_disebabkan", PENYEBAB, "Kerusakan Disebabkan", False),
    ]
