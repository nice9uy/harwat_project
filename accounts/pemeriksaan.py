"""Fixed choices and checklist of the vehicle inspection form (Form Pemeriksaan)."""

PEMBAGIAN_KELAS = ["1", "2", "3", "4", "5", "6"]
ESELON_REPARASI = ["1", "2", "3", "4"]
MACAM_PEMERIKSAAN = [("tehnis", "Tehnis"), ("tiba_tiba", "Tiba-tiba")]
BUKU_JALAN = [("ada", "Ada"), ("tidak", "Tidak")]
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


# --- Kendaraan Bermotor (paper form with 63 components) ---

KONDISI_BERMOTOR = [
    ("B", "Baik"),
    ("HP", "Harus Diperbaiki"),
    ("HG", "Harus Diganti"),
    ("TA", "Tidak Ada"),
]
BUKU_HARIAN = BUKU_JALAN

KOMPONEN_BERMOTOR = [
    "Mesin / Tune Up / Over Haul", "Head Cylinder / Blok Cylinder / Carter", "Piston Assy",
    "Intake Valve / Exhaust Valve", "Noken As, Rocker Arm", "Valve Assy", "Poros Engkol, Flywheel",
    "Timing Chain / Timing Belt", "Pulley", "Drive Belt", "Engine Mounting",
    "Electronic Control Unit (ECU)", "CDI", "Busi/Pijar, Kabel Busi & Koil",
    "Intake Manifold / Exhaust Manifold", "Karburator / Injector", "Pompa Bahan Bakar", "Radiator",
    "Selang / Hose", "Cooling Fan", "Thermostat", "Reservoir Tank", "Alternator / Regulator", "Accu",
    "Stater Assy", "Bandic Stater", "Transmisi", "Propeler Shaft Dpn / Blkg",
    "Kopling Assy (Plat, Dekrup, Druklaher)", "Master Kopling / Master Rem",
    "Minyak Kopling / Minyak Rem", "Brake Pad / Brake Shoe",
    "Oli Mesin", "Oli Persneling / Transmisi", "Oli Gardan", "Filter Set (AC, Oli, BBM, Udara)",
    "Shock Breaker", "Support Shock Breaker", "Lagher Roda", "Rack End, Rack Steering", "Ball Joint",
    "Tie Rod, Long Tie Rod", "Stabilizer, Link Stabilizer", "Lower Arm, Upper Arm", "Power Steering",
    "Sistem Kemudi", "Kabel Kelistrikan", "Box Sekring", "Sekring, Fuse, Relay",
    "Lampu Besar, Sein, Rem, Hazard", "Rotator / Sirine", "Cat Body, Bumper, Kap Mesin",
    "Pintu, Handle", "Central Lock", "Air Conditioner", "Speedo Meter", "Seat / Seat Belt",
    "Ban Depan / Belakang / Kanan / Kiri", "Ban Cadangan", "Dongkrak", "Tabung Pemadam",
    "Kotak P3K", "Winch",
]
KOMPONEN_BERMOTOR_BERNOMOR = list(enumerate(KOMPONEN_BERMOTOR, start=1))

# Badge colours per kondisi code, for both forms. Full class strings so
# Tailwind's scanner picks them up from this file.
KONDISI_WARNA = {
    "B": "bg-green-600",
    "RR": "bg-amber-500",
    "HP": "bg-amber-500",
    "RB": "bg-red-600",
    "HG": "bg-red-600",
    "TA": "bg-slate-500",
}
KONDISI_WARNA_DIPILIH = {
    "B": "has-checked:border-green-600 has-checked:bg-green-600",
    "RR": "has-checked:border-amber-500 has-checked:bg-amber-500",
    "HP": "has-checked:border-amber-500 has-checked:bg-amber-500",
    "RB": "has-checked:border-red-600 has-checked:bg-red-600",
    "HG": "has-checked:border-red-600 has-checked:bg-red-600",
    "TA": "has-checked:border-slate-500 has-checked:bg-slate-500",
}
