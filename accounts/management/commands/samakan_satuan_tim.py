"""Brings every Tim member's Satuan onto their Ketua Tim's (accounts/satuan_tim.py),
for the data from before the rule. Shows what would change unless --terapkan.

    python manage.py samakan_satuan_tim              # what would change
    python manage.py samakan_satuan_tim --terapkan   # change it
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts import satuan_tim
from accounts.models import AkunPublik, Anggota, Laporan, Satuan


class Command(BaseCommand):
    help = "Samakan satuan anggota tim dengan satuan Ketua Tim-nya."

    def add_arguments(self, parser):
        parser.add_argument("--terapkan", action="store_true", help="benar-benar ubah (tanpa ini: hanya tampilkan)")

    def handle(self, terapkan=False, **options):
        nama = dict(Satuan.objects.values_list("pk", "nama"))
        beda = 0
        for ketua in Anggota.objects.filter(depth=1).select_related("user"):
            satuan = satuan_tim.satuan_ketua(ketua.user)
            if not satuan:
                self.stdout.write(f"- Ketua Tim {ketua.user.username}: belum punya satuan, timnya dilewati")
                continue
            for anggota in ketua.get_children().select_related("user"):
                lama = set(Laporan.objects.filter(akun=anggota.user).values_list("satuan", flat=True))
                lama |= set(AkunPublik.objects.filter(user=anggota.user).exclude(satuan=None).values_list("satuan", flat=True))
                if lama and lama != {satuan}:
                    beda += 1
                    self.stdout.write(
                        f"  {anggota.user.username}: {', '.join(nama.get(s, '-') for s in sorted(lama))} -> {nama[satuan]}"
                        f" (Ketua Tim {ketua.user.username})"
                    )
        if not terapkan:
            self.stdout.write(f"{beda} anggota akan dipindah satuannya. Jalankan dengan --terapkan untuk mengubah.")
            return
        with transaction.atomic():
            diubah = sum(satuan_tim.samakan_tim(k.user) for k in Anggota.objects.filter(depth=1).select_related("user"))
        self.stdout.write(f"Selesai: {diubah} data (akun dan biodata) dipindah ke satuan Ketua Tim.")
