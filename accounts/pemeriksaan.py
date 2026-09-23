"""Fixed choices and checklist of the vehicle inspection form (Form Pemeriksaan)."""

PEMBAGIAN_KELAS = ["1", "2", "3", "4", "5", "6"]
ESELON_REPARASI = ["1", "2", "3", "4"]
MACAM_PEMERIKSAAN = [("tehnis", "Tehnis"), ("tiba_tiba", "Tiba-tiba")]
KONDISI = [("B", "Baik"), ("RR", "Rusak Ringan"), ("RB", "Rusak Berat")]

# Numbered as on the paper form. On the paper sheet "Carburator" and "Busi"
# are struck through, leaving Injeksi Pump and Nozzle.
ALAT = [
    "Motor", "Kopling", "Injeksi Pump", "Nozzle", "Kabel Busi",
    "Saringan BBM", "Sistim Pendingin", "Sistim Pelumasan", "Sistim Kemudi", "Saringan Udara",
    "Speedometer", "Rem Tangan", "Rem Kaki", "Shock Absorber Front", "Shock Absorber Rear",
    "Roda Velg", "Ban Depan", "Ban Belakang", "Gear Depan", "Gear Belakang",
    "Rantai", "Sistem Kelistrikan", "Lampu Besar", "Lampu Rem", "Lampu Sign",
    "Motor Starter", "Klakson", "Accu", "Kaca Spion", "Kursi / Jok",
    "Sekring", "Tanki BBM", "Stering Arm", "Spakboard", "Cabin / Body",
    "Standar", "Footstep", "Peredam Letus", "Chasis", "Cat",
]

ALAT_BERNOMOR = list(enumerate(ALAT, start=1))
