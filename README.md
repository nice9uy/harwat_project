# Harwat

Aplikasi Pemeliharaan dan Perawatan Kendaraan dan Non Kendaraan: pendataan kendaraan,
pemeriksaan, perbaikan, kendaraan rusak/tidak layak pakai, laporan, dan dashboard per matra.

Dibangun dengan Django + django-bolt, HTMX, Alpine.js, dan Tailwind CSS. Seluruh layanan
(aplikasi, PostgreSQL + PgBouncer, Valkey, Garage, WireGuard, nginx) berjalan di Podman.

## Menjalankan

Cukup satu perintah. Dijalankan dari folder proyek, di Linux:

```bash
./dev.sh    # pengembangan: kode langsung dari folder ini, muat ulang otomatis, DEBUG aktif
./prod.sh   # produksi: image dibangun, 3 replika aplikasi di belakang nginx
```

| | `./dev.sh` | `./prod.sh` |
|---|---|---|
| Alamat | http://localhost:8001 | http://localhost:8000 dan https://localhost:8443 |
| Database | SQLite (`db.sqlite3`) | PostgreSQL (1 primary + 2 replica) |
| Foto | folder `media/` | bucket Garage |
| Pengaturan | `.env.dev` (disalin dari `.env.dev.example`) | `.env.prod` (dibuat otomatis) |
| Berjalan di | terminal (Ctrl+C untuk berhenti) | latar belakang |

Yang dikerjakan kedua skrip secara otomatis, sehingga tidak perlu disiapkan dulu:

1. **Memasang komponen yang belum ada** (`scripts/pasang-komponen.sh`): podman,
   podman-compose, curl, dan untuk produksi juga openssl dan envsubst — beserta paket
   pendamping podman tanpa root dan rentang sub-id pengguna. Pengelola paket yang dikenali:
   apt, dnf, yum, zypper, pacman, apk. Pemasangan memakai `sudo`, jadi bisa meminta password.
   Mesin yang sudah lengkap tidak diubah apa pun.
2. **Membangun CSS** (`scripts/build-css.sh`) bila `static/dist/output.css` belum ada.
   Binary Tailwind diunduh sendiri ke `bin/`.
3. **Mematikan kontainer yang sedang berjalan**, lalu menjalankannya ulang. Hanya kontainer
   aplikasi ini yang disentuh; kontainer proyek lain dan semua volume (data) dibiarkan.
4. **Menjalankan migrasi database.**

Untuk melihat apa yang akan dipasang tanpa memasangnya:

```bash
PASANG_SIMULASI=1 bash -c 'source scripts/pasang-komponen.sh; pasang_komponen podman podman-compose curl openssl envsubst'
```

### Catatan pengembangan (`./dev.sh`)

- Dev dan produksi memakai nama kontainer yang sama, jadi **tidak bisa berjalan bersamaan**:
  menjalankan yang satu mematikan yang lain.
- Agar bisa dibuka dari HP di jaringan yang sama, pakai alamat IP yang dicetak skrip.
- Untuk tunnel HTTPS (localtonet, ngrok), isi dulu alamatnya:
  `DJANGO_CSRF_TRUSTED_ORIGINS=https://alamat-tunnel ./dev.sh`
- Menu **Server** menampilkan daftar kontainer lewat `podman.socket`; skrip mencoba
  mengaktifkannya (`systemctl --user enable --now podman.socket`).
- Setelah mengubah template atau kelas Tailwind, bangun ulang CSS: `./scripts/build-css.sh`

### Catatan produksi (`./prod.sh`)

- Pada jalan pertama skrip membuat `.env.prod` berisi semua rahasia (kunci Django, password
  database, kunci Garage, kunci WireGuard). **Cadangkan berkas ini**; ia tidak masuk git.
  Jalan berikutnya hanya menambah pengaturan yang belum ada dan tidak pernah menimpa isinya.
- Isi sendiri di `.env.prod`:
  - `DJANGO_ALLOWED_HOSTS` — nama domain atau IP server (bawaan hanya `localhost,127.0.0.1`).
  - `VPN_SERVER_ENDPOINT=<ip-publik>:51820` — tanpa ini config VPN anggota tidak bisa dipakai.
- Setelah kontainer hidup, skrip menjalankan migrasi, menulis config server WireGuard, mengisi
  daftar satuan (Kodam, Korem, Kodim, Koramil), dan menghitung ulang status kendaraan.
- Di akhir, skrip mencetak kontainer yang berjalan dan status replikasi database
  (seharusnya 2 baris `streaming`).

## HTTPS (mkcert)

Produksi melayani HTTP di port 8000 dan HTTPS di port 8443. Sertifikatnya dibuat otomatis oleh
`./prod.sh` (`scripts/siapkan-tls.sh`) dengan mkcert, untuk `localhost`, nama mesin, dan semua
alamat IP mesin itu. mkcert diunduh sendiri ke `bin/` bila belum terpasang. Sertifikat dibuat
ulang hanya bila alamat mesin berubah atau masa berlakunya hampir habis.

Sertifikat ini ditandatangani otoritas lokal, bukan otoritas publik, jadi browser akan memberi
peringatan sampai otoritas itu diimpor **di tiap perangkat yang membuka aplikasi**:

1. Unduh `http://<alamat-server>:8000/rootCA.pem`.
2. Impor sebagai otoritas tepercaya:
   - Chrome/Edge: Settings → Privacy and security → Security → Manage certificates →
     Authorities → Import, centang "Trust this certificate for identifying websites".
   - Firefox: Settings → Privacy & Security → Certificates → View Certificates → Authorities → Import.
   - Android: Settings → Security → Encryption & credentials → Install a certificate → CA certificate.
   - Windows: klik dua kali berkasnya → Install Certificate → Trusted Root Certification Authorities.
3. Buka `https://<alamat-server>:8443`.

Nama atau alamat tambahan (mis. domain atau IP publik): `TLS_NAMA="harwat.lan 203.0.113.7" ./prod.sh`.
Folder `podman/tls/` berisi kunci sertifikat dan kunci otoritas; ia tidak masuk git dan jangan dibagikan.

## Data produksi

- **Database** — PostgreSQL 17. `postgres` adalah primary; aplikasi membaca dan menulis lewat
  `pgbouncer`. `postgres-replica1` dan `postgres-replica2` adalah salinan baca-saja yang
  mengikuti primary (streaming replication). Aplikasi tidak membaca dari replica. Cek:

  ```bash
  podman exec podman_postgres_1 psql -U bmn_harwat -d bmn_harwat -c "select client_addr, state from pg_stat_replication"
  ```

  **Failover manual**: bila primary hilang, naikkan satu replica
  (`podman exec podman_postgres-replica1_1 gosu postgres pg_ctl promote -D /var/lib/postgresql/data`)
  lalu arahkan `DB_HOST` milik `pgbouncer` ke replica itu. Tidak ada yang melakukannya otomatis.
- **Foto** — disimpan di bucket Garage (`harwat_main/storage.py`) dan disajikan lewat
  `/media/...` hanya untuk pengguna yang sudah login.
- **Backup** — dibuat dari menu Backup (khusus superuser), tersimpan di volume backup.
- **Pindahan dari susunan lama** — jalan pertama `./prod.sh` menyalin foto dari kontainer lama
  ke `migrasi/media/`, lalu `manage.py impor_sqlite` (SQLite lama → PostgreSQL, hanya ke
  database kosong) dan `manage.py impor_media` (foto → Garage). Aman diulang.
- **nginx** membagi beban ke tiga replika aplikasi (`app1`, `app2`, `app3`) dan menyajikan
  `/static/` langsung dari volume bersama.

## VPN (WireGuard)

Anggota tim tersambung lewat WireGuard. Config tiap anggota (QR code, teks untuk disalin, dan
berkas unduhan) ada di kolom VPN pada menu Anggota Tim. Jaringan `VPN_SUBNET` (bawaan
`10.13.0.0/20`) cukup untuk sekitar 4.000 anggota. Akun yang dinonaktifkan tidak bisa login
walaupun VPN-nya masih tersambung.

## Peran pengguna

| Peran | Yang bisa dilakukan |
|---|---|
| Superuser | Semua menu, termasuk Kendaraan, Non Kendaraan, Form Group, Server, Backup, Admin Panel |
| Admin | Mengelola pengguna dan satuan, laporan, dashboard matranya sendiri |
| Pimpinan | Melihat dashboard semua matra, laporan, jadwal, servis (tanpa form dan pengaturan) |
| Pimpinan Ketua Tim | Melihat tim para Ketua Tim yang dipilihnya, dashboard matranya sendiri |
| Ketua Tim | Mengelola anggota timnya, melihat laporan dan dashboard timnya |
| Tim Pemeriksaan | Form Pemeriksaan |
| Tim Perbaikan | Form Perbaikan |
| Tim Penambahan Data | Form Tambah |
| Tim Pemeriksaan Rusak/Tidak Layak | Form Rusak/Tidak Layak Pakai |

Akun Pimpinan hanya bisa dibuat, diubah, dan dihapus oleh superuser. Password awal akun baru
adalah `12345` — minta setiap pengguna menggantinya lewat menu Ganti Password.

Golongan kendaraan: Golongan B, Motor, Kendaraan Diesel, Jeep Diesel, RANPUR, RANTIS, RANSUS,
RANUM. Form pemeriksaan tersedia untuk semuanya kecuali RANPUR dan RANUM.

## Mengembangkan tanpa Podman

```bash
uv sync
./scripts/build-css.sh
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Menjalankan test:

```bash
uv run python manage.py test accounts fleet
```

Sebagian test lama masih gagal (alur biodata, captcha, menu Tim) dan belum diperbaiki; saat
mengubah kode, bandingkan daftar test yang gagal sebelum dan sesudahnya.

## Susunan folder

| Folder / berkas | Isi |
|---|---|
| `accounts/` | Pengguna dan peran, form pemeriksaan/perbaikan/rusak, laporan, dashboard, VPN, backup |
| `fleet/` | Kendaraan, jadwal, servis, QR code, API |
| `harwat_main/` | Pengaturan Django, URL, penyimpanan foto |
| `templates/`, `static/` | Tampilan (HTMX, Alpine.js, Tailwind) |
| `podman/` | Berkas compose, nginx, PostgreSQL, Garage, WireGuard |
| `scripts/` | `build-css.sh`, `pasang-komponen.sh` |
| `docs/` | Catatan rancangan infrastruktur |
