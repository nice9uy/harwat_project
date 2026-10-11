import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from accounts.models import Satuan

BERKAS = Path(__file__).resolve().parents[2] / "data" / "satuan_tni_ad.csv"


class Command(BaseCommand):
    help = (
        "Isi Pengaturan > Satuan dengan Kodam, Korem, Kodim dan Koramil dari "
        "accounts/data/satuan_tni_ad.csv. Aman diulang: satuan yang namanya sudah ada dilewati."
    )

    def add_arguments(self, parser):
        parser.add_argument("berkas", nargs="?", default=str(BERKAS), help="CSV berkolom jenis,nama,keterangan")

    def handle(self, *args, **options):
        with open(options["berkas"], newline="") as f:
            baris = list(csv.DictReader(f))
        ada = set(Satuan.objects.values_list("nama", flat=True))
        baru = [
            Satuan(nama=b["nama"].strip(), keterangan=b.get("keterangan", "").strip())
            for b in baris if b["nama"].strip() and b["nama"].strip() not in ada
        ]
        Satuan.objects.bulk_create(baru, batch_size=500)
        per_jenis = {}
        for b in baris:
            per_jenis[b["jenis"]] = per_jenis.get(b["jenis"], 0) + 1
        rincian = ", ".join(f"{n} {j.title()}" for j, n in per_jenis.items())
        self.stdout.write(f"{len(baru)} satuan ditambahkan, {len(baris) - len(baru)} sudah ada ({rincian} di berkas).")
