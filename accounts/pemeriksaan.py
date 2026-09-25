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
    "ADA": "bg-sky-600",
}
KONDISI_WARNA_DIPILIH = {
    "B": "has-checked:border-green-600 has-checked:bg-green-600",
    "RR": "has-checked:border-amber-500 has-checked:bg-amber-500",
    "HP": "has-checked:border-amber-500 has-checked:bg-amber-500",
    "RB": "has-checked:border-red-600 has-checked:bg-red-600",
    "HG": "has-checked:border-red-600 has-checked:bg-red-600",
    "TA": "has-checked:border-slate-500 has-checked:bg-slate-500",
    "ADA": "has-checked:border-sky-600 has-checked:bg-sky-600",
}


# --- Kendaraan Diesel (paper form grouped into chapters and systems) ---

KONDISI_DIESEL = [
    ("B", "Baik"),
    ("RR", "Rusak Ringan"),
    ("RB", "Rusak Berat"),
    ("ADA", "Ada"),
    ("TA", "Tidak Ada"),
]

YA_TIDAK = [("ya", "Ya"), ("tidak", "Tidak")]
KONDISI_RANMOR = [("jalan", "Jalan"), ("tidak", "Tidak")]

BAGIAN_DIESEL = [
    ("I", "Power Plant", [
        ("A", "Engine System", [
            "Block Mesin", "Cylinder Head", "Tutup Cylinder Head", "Stik Penduga Oli", "Carter",
            "Intake Manipold", "Exhaust Manipold", "Pulley Crack Shaft",
        ]),
        ("B", "Air Cleaner Intake System", ["Rumah Filter Udara", "Element Filter Udara", "Hose Filter Udara"]),
        ("C", "Exhaust System", ["Knalpot", "Pipa Knalpot Belakang", "Pipe Extension", "Exhaust Pipe"]),
        ("D", "Fuel System", [
            "Air Cleaner Assembly", "Kabel Pedal Gas", "Tanki Bahan Bakar", "Tutup Tanki Bahan Bakar",
            "Pompa Injeksi", "Gelas Feed Pump Assy", "Pipa Fuel Pump", "Nozel", "Pipa Nozzel",
            "Water Separator", "Hose Fuel",
        ]),
        ("E", "Cooling System", [
            "Radiator Assembly", "Selang Radiator Assembly Outlet", "Selang Inlet Upper", "Radiator Grill",
            "Radiator Fan", "Radiator Fulley", "Tutup Radiator", "Water Pump", "Reservoir Tank", "Fanbelt",
            "Thermosthat", "Fulley Water Pump", "Pelindung Kipas Radiator",
        ]),
        ("F", "Lubrication System", ["Filter Oil", "Pipe Oil Filter", "Gage Oil Level"]),
    ]),
    ("II", "Power Train", [
        ("A", "Clutch System", [
            "Cover Clutch", "Disc Clutch", "Pedal Clutch", "Blacket Assembly Clutch Pedal",
            "Bell Crank Assembly Clutch Pedal", "Link Clutch Release", "Rod Assembly Clutch Release",
            "Shaft Ang Level Assembly Clutch Release", "Sleve Assembly Clutch Release", "Release Bearing",
        ]),
        ("B", "Transmission System", [
            "Transmission Assembly", "Tuas Perseneleng Assy", "Karet Pelindung Tuas Perseneleng",
        ]),
        ("D", "Propeller Shaft System", ["Propeller Shaft Depan", "Propeller Shaft Belakang"]),
        ("E", "Axle System", [
            "Differential Front Assy", "Differential Rear Assy", "As Roda Depan Ki/Ka", "As Roda Belakang Ki/Ka",
            "Seal Roda Depan Ki/Ka", "Seal Roda Belakang Ki/Ka",
        ]),
        ("F", "Wheel, Tire and Suspension", [
            "Ban", "Velg", "Ban Cadangan", "Dudukan Ban Cadangan", "Shock Absorber Depan Ki/Ka",
            "Shock Absorber Belakang Ki/Ka", "Per Depan Ki/Ka", "Per Belakang Ki/Ka",
        ]),
    ]),
    ("III", "Control System", [
        ("A", "Steering Sistem", [
            "Steering Wheel", "Steering Column Assembly", "Steering Power Pump", "Steering Gear",
            "Reservoir Liquid Pump", "Track Rod Tube Assembly", "Tierod Assembly", "Steering Damper",
        ]),
        ("B", "Brake Sistem", [
            "Tuas Rem Tangan", "Sambungan Hand Brake to Transfer", "Master Cylinder Rem Atas Assy",
            "Wheel Cylinder Rem Assy", "Pedal Rem", "Karet Pedal Rem", "Servo Hand Brake", "Tanki Udara",
            "Reservoir Oil Tank", "Flexible Depan", "Flexible Belakang", "Boster Rem",
        ]),
    ]),
    ("IV", "Electrical System", [
        ("A", "Sistem Injeksi", ["Stop Engine", "Rpm"]),
        ("B", "Sistem Pengisian", ["Alternator", "Regulator", "Battere", "Kabel Battere (+/-)"]),
        ("C", "Sistem Stater", ["Motor Stater", "Rilley Stater", "Konci Kontak"]),
        ("D", "Arus Penolong", [
            "Head Lamp", "Side Lamp", "Tail Lamp", "Stop Lamp", "Turn Lamp", "Horn", "Dashboard/Assy",
            "Spedometer", "Fuel Meter", "Temp Meter", "Oil Meter", "Ind Dashboard", "Lampu Kabin",
            "Turn Switch", "Motor Wiper", "Blade Wiper", "Arm Wiper", "Spion Luar Ki/Ka",
            "Dudukan Spion Luar Ki/Ka Assy", "Spion Dalam", "Blower Ventilator", "Blower Heater", "AC",
        ]),
    ]),
    ("V", "Frame, Suspension, Body, Cab and Hood", [
        ("", "", [
            "Chassis Frame", "Bemper Depan", "Bemper Belakang", "Kaca Flame Depan", "Towing Hook Assy",
            "Kanopi", "Rangka Kanopi", "Tempat Duduk Personil Blk Ki/Ka", "Pintu Bak Belakang",
            "Injakan Personil Belakang", "Tutup Box Battery", "Hidrolic Kabin", "Pintu Depan Samping Ki/Ka",
            "Pembuka Pintu Depan Ki/Ka", "Pemutar Kaca Pintu Depan Ki/Ka", "Regulator Kaca Depan Samping Ki/Ka",
            "Sabuk Pengaman", "Jok Depan Ki/Ka",
        ]),
    ]),
]


def _diesel_bernomor():
    """Chapters with their systems and parts, each part numbered 1..n across the form."""
    nomor, bab_list, rata = 0, [], []
    for bab, judul, sistem_list in BAGIAN_DIESEL:
        sistem_out = []
        for huruf, sistem, parts in sistem_list:
            items = []
            for lokal, nama in enumerate(parts, start=1):
                nomor += 1
                items.append((nomor, lokal, nama))
                rata.append((nomor, nama))
            sistem_out.append((huruf, sistem, items))
        bab_list.append((bab, judul, sistem_out))
    return bab_list, rata


DIESEL_BAB, KOMPONEN_DIESEL_BERNOMOR = _diesel_bernomor()
