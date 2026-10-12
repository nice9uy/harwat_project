"""Fixed choices and checklist of the vehicle inspection form (Form Pemeriksaan)."""

PEMBAGIAN_KELAS = ["1", "2", "3", "4", "5", "6"]
ESELON_REPARASI = ["1", "2", "3", "4"]
MACAM_PEMERIKSAAN = [("tehnis", "Tehnis"), ("tiba_tiba", "Tiba-tiba")]
BUKU_JALAN = [("ada", "Ada"), ("tidak", "Tidak")]
KONDISI = [("B", "Baik"), ("RR", "Rusak Ringan"), ("RB", "Rusak Berat"), ("ADA", "Ada"), ("TA", "Tidak Ada")]

# What a repair leaves a part in (Form Perbaikan), on every vehicle group.
# Stored under the inspection codes B / RR / RB, so the rest (a part still
# not Baik stays on the repair list) works as before; a repair saved before
# these names may still hold ADA or TA.
KONDISI_PERBAIKAN = [("B", "Baik"), ("RR", "Perlu Servis"), ("RB", "Rusak")]
KONDISI_PERBAIKAN_LAMA = [("ADA", "Ada"), ("TA", "Tidak Ada")]
# The letters on the form's three buttons.
SINGKATAN_PERBAIKAN = {"B": "B", "RR": "PS", "RB": "R"}

KESIMPULAN = [
    ("siap_pakai", "Siap Pakai"),
    ("perlu_perbaikan", "Perlu Perbaikan"),
    ("tidak_layak_pakai", "Tidak Layak Pakai"),
]

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


# --- Motor (62 components: the paper form's, less Minyak Kopling / Minyak Rem) ---

KONDISI_BERMOTOR = [
    ("B", "Baik"),
    ("RR", "Rusak Ringan"),
    ("RB", "Rusak Berat"),
    ("ADA", "Ada"),
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
    "Brake Pad / Brake Shoe",
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

# The oil parts, marked * on the form: they go into the Jadwal for a check
# (their intervals are set in Pengaturan > KM).
KOMPONEN_BERMOTOR_KM = {"Oli Mesin", "Oli Persneling / Transmisi", "Oli Gardan"}
# Header fields marked * the same way (they have no part number): Golongan
# B's and Motor's KM Kendaraan, and Km / Mil on Kendaraan Diesel
# and Jeep Diesel.
KM_GOLONGAN_B = "KM Kendaraan"
KM_DIESEL = "Km / Mil"
BERMOTOR_KM_NOMOR = frozenset(nomor for nomor, nama in KOMPONEN_BERMOTOR_BERNOMOR if nama in KOMPONEN_BERMOTOR_KM)

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


def _diesel_bernomor(bagian):
    """Chapters with their systems and parts, each part numbered 1..n across the form."""
    nomor, bab_list, rata = 0, [], []
    for bab, judul, sistem_list in bagian:
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


DIESEL_BAB, KOMPONEN_DIESEL_BERNOMOR = _diesel_bernomor(BAGIAN_DIESEL)


# --- Jeep Diesel (same paper layout as Kendaraan Diesel, its own parts) ---

# The paper form has no Baik column; it was asked for, as on Kendaraan Diesel.
KONDISI_JEEP_DIESEL = [
    ("B", "Baik"),
    ("RR", "Rusak Ringan"),
    ("RB", "Rusak Berat"),
    ("ADA", "Ada"),
    ("TA", "Tidak Ada"),
]

# Names as on the paper form. Its Electrical System is section C of Control
# System, itself split into I-IV.
BAGIAN_JEEP_DIESEL = [
    ("I", "Power Plant", [
        ("A", "Engine System", ["Block Mesin Assy", "Cylinder Head Assy", "Stik Penduga Oli", "Carter"]),
        ("B", "Air Cleaner Intake System", ["Rumah Filter Udara", "Element Filter Udara", "Hose Filter Udara"]),
        ("C", "Exhaust System", ["Muffler", "Tail Pipe Assembly", "Pipe Extension", "Exhaust Pipe", "Packing"]),
        ("D", "Fuel System", [
            "Fuel Tank", "Tutup Fuel Tank", "Hose Fuel", "Filter Fuel Tank", "Pompa Injection", "Nozzle",
        ]),
        ("E", "Cooling System", [
            "Radiator Assembly", "Hose Radiator Assembly Outlet", "Hose Inlet Upper", "Radiator Grill Panel",
            "Radiator Fan", "Radiator Fulley", "Fan Belt", "Thermosthat", "Rumah Thermosthat", "Water Pump",
        ]),
        ("F", "Lubrication System", ["Oil Filter Assembly", "Gauge Oil Level"]),
    ]),
    ("II", "Power Train", [
        ("A", "Clutch System", [
            "Cover Clutch", "Disc Clutch", "Pedal Clutch", "Master Kopling Atas", "Master Kopling Bawah",
            "Clutch Housing Assy",
        ]),
        ("B", "Transmission System", ["Gear Box Assy", "Tuas Gigi Percepatan"]),
        ("C", "Transfer Case", ["Gear Box Assy", "Tuas Gigi Low / High"]),
        ("D", "Propeller Shaft System", ["Propeller Shaft Front", "Propeller Shaft Real"]),
        ("E", "Axle System", ["Axle Depan", "Axle Belakang"]),
        ("F", "Wheel and Tire", [
            "Per Depan", "Per Belakang", "Sock Absorber Depan", "Sock Absorber Belakang", "Stabilizer", "Ban",
            "Velg", "Ban Cadangan & Velg",
        ]),
    ]),
    ("III", "Control System", [
        ("A", "Steering Sistem", [
            "Steering Wheel", "Steering Lube", "Power Steering", "Pompa Power Steering",
            "Tabung Minyak Power Steering", "Rilay Rol", "Therod End", "Stabilizer Steering",
        ]),
        ("B", "Brake Sistem", ["Pedal Rem", "Master Rem Atas", "Tabung Minyak Rem", "Boster Rem", "Wheel Master Rem"]),
        ("C.I", "Electrical System: Sistem Injeksi", ["Stop Engine", "RPM"]),
        ("C.II", "Electrical System: Sistem Pengisian", ["Alternator", "Regulator", "Battere", "Kabel Battere (+/-)"]),
        ("C.III", "Electrical System: Sistem Stater", ["Motor Stater", "Rilley Stater", "Konci Kontak"]),
        ("C.IV", "Electrical System: Aksesoris", [
            "Head Lamp", "Side Lamp", "Tail Lamp", "Stop Lamp", "Turn Lamp", "Horn", "Dashboard/Assy",
            "Spedometer", "Fuel Meter", "Temp Meter", "Oil Meter", "Ind Dashboard", "Lampu Kabin", "Turn Switch",
            "Motor Wiper", "Blade Wiper", "Arm Wiper", "Black Out", "Replector", "Spion Luar", "Spion Dalam", "AC",
        ]),
    ]),
    ("IV", "Frame, Suspension, Body, Cab and Hood", [
        ("", "", [
            "Rangka", "Kap Mesin", "Bemper Depan", "Kaca Depan", "Spark Board", "Pintu Kanan", "Pintu Kiri",
            "Ruang Kabin", "Jok Depan", "Spion Dalam", "Spion Luar", "Kaca Pintu Depan", "Kaca Pintu Kiri", "Body",
            "Bemper Belakang", "Pintu Belakang",
        ]),
    ]),
]

JEEP_DIESEL_BAB, KOMPONEN_JEEP_DIESEL_BERNOMOR = _diesel_bernomor(BAGIAN_JEEP_DIESEL)

# --- RANTIS (same paper layout as Jeep Diesel, its own parts) ---

# With Baik, as on the other forms of this layout.
KONDISI_RANTIS = KONDISI_JEEP_DIESEL

# Names as on the paper form. Its Electrical System is section C of Control
# System, itself split into I-IV.
BAGIAN_RANTIS = [
    ("I", "Power Plant", [
        ("A", "Engine System", ["Block Mesin Assy", "Cylinder Head Assy", "Stik Penduga Oli", "Carter"]),
        ("B", "Air Cleaner Intake System", ["Rumah Filter Udara", "Element Filter Udara", "Hose Filter Udara"]),
        ("C", "Exhaust System", ["Muffler", "Tail Pipe Assembly", "Pipe Extension", "Exhaust Pipe", "Packing"]),
        ("D", "Fuel System", [
            "Fuel Tank", "Tutup Fuel Tank", "Hose Fuel", "Filter Fuel Tank", "Pompa Injection", "Nozzle",
            "Pompa Tekanan Tinggi", "Pompa Tekanan Rendah", "Common Rail",
        ]),
        ("E", "Cooling System", [
            "Radiator Assembly", "Hose Radiator Assembly Outlet", "Hose Inlet Upper", "Radiator Grill Panel",
            "Radiator Fan", "Radiator Fulley", "Fun Belt", "Thermosthat", "Rumah Thermosthat", "Water Pump",
        ]),
        ("F", "Lubrication System", ["Oil Filter Assembly", "Gauge Oil Level"]),
    ]),
    ("II", "Power Train", [
        ("A", "Clutch System", [
            "Cover Clutch", "Disc Clutch", "Pedal Clutch", "Master Kopling Atas", "Master Kopling Bawah",
            "Clutch Housing Assy",
        ]),
        ("B", "Transmission System", ["Gear Box Assy", "Tuas Gigi Percepatan"]),
        ("C", "Transfer Case", ["Gear Box Assy", "Tuas Gigi Low / High"]),
        ("D", "Propeller Shaft System", ["Propeller Shaft Front", "Propeller Shaft Real"]),
        ("E", "Axle System", ["Axle Depan", "Axle Belakang"]),
        ("F", "Wheel and Tire", [
            "Per Depan", "Per Belakang", "Sock Absorber Depan", "Sock Absorber Belakang", "Stabilizer", "Ban",
            "Velg", "Ban Cadangan & Velg",
        ]),
    ]),
    ("III", "Control System", [
        ("A", "Steering Sistem", [
            "Steering Wheel", "Steering Lube", "Power Steering", "Pompa Power Steering",
            "Tabung Minyak Power Steering", "Rilay Rol", "Therod End", "Stabilizer Steering",
        ]),
        ("B", "Brake Sistem", ["Pedal Rem", "Master Rem Atas", "Tabung Minyak Rem", "Boster Rem", "Wheel Master Rem"]),
        ("C.I", "Electrical System: Sistem Injeksi", ["Stop Engine", "RPM"]),
        ("C.II", "Electrical System: Sistem Pengisian", ["Alternator", "Regulator", "Battere", "Kabel Battere (+/-)"]),
        ("C.III", "Electrical System: Sistem Stater", ["Motor Stater", "Rilley Stater", "Konci Kontak"]),
        ("C.IV", "Electrical System: Arus Penolong", [
            "ECU Assy", "Head Lamp", "Side Lamp", "Tail Lamp", "Stop Lamp", "Turn Lamp", "Horn", "Dashboard/Assy",
            "Spedometer", "Fuel Meter", "Temp Meter", "Oil Meter", "Ind Dashboard", "Lampu Kabin", "Turn Switch",
            "Motor Wiper", "Blade Wiper", "Arm Wiper", "Black Out", "Replector", "Spion Luar", "Spion Dalam", "AC",
        ]),
    ]),
    ("IV", "Frame, Suspension, Body, Cab and Hood", [
        ("", "", [
            "Rangka", "Kap Mesin", "Bemper Depan", "Kaca Depan", "Spark Board", "Pintu Kanan", "Pintu Kiri",
            "Ruang Kabin", "Jok Depan", "Spion Dalam", "Spion Luar", "Kaca Pintu Depan", "Kaca Pintu Kiri", "Body",
            "Bemper Belakang", "Pintu Belakang",
        ]),
    ]),
]

RANTIS_BAB, KOMPONEN_RANTIS_BERNOMOR = _diesel_bernomor(BAGIAN_RANTIS)

# --- RANSUS (kendaraan khusus: the equipment list of its paper form) ---

KONDISI_RANSUS = KONDISI_JEEP_DIESEL

# One flat list of 40 pieces of equipment, numbered as on the paper form; in
# the diesel layout it is a single chapter with one unnamed system.
PERALATAN_RANSUS = [
    'Selang Penyalur (Fire Hose) Ukuran 2½" x 20 Meter',
    'Selang Penyalur (Fire Hose) Ukuran 1½" x 20 Meter',
    'Selang Hisap (Suction Hose) Ukuran 6" x 2,5 meter',
    "Saringan Metal",
    "Saringan Rotan",
    "Kunci Kopling Selang Hisap",
    "Kunci Hidran",
    'Pipa Cabang (Branch Pipe) Ukuran: 2,5"-2,5"-2,5"',
    'Pipa Cabang (Branch Pipe) Ukuran: 2,5"-1,5"-1,5"',
    "Pemancar (Nozzle) Variabel Ukuran 2,5 inch YVH Coupling",
    "Pemancar (Nozzle) Variabel Ukuran 1,5 inch YVH Coupling",
    "Pemancar (Nozzle) Foam Ukuran 2,5 inch YVH Coupling",
    "Pemancar Gambut (Pearching Nozzle) Ukuran 1,5 inch",
    'Kopling Peningkat (Adaptor) dari 4"-2,5"',
    "Adaptor Kopling YVH ke Machino Ukuran 2,5 inch",
    "Adaptor Kopling YVH ke Machino Ukuran 1,5 inch",
    'Adaptor Kopling Ulir - YVH Ukuran 2,5"',
    "APAR (Alat Pemadam Api Ringan) ABC Dry Chemical Powder, Multi Purpose (4,5-6 kg)",
    "Cairan Busa (Foam Liquid)",
    "Kapak Besar",
    "Sekop Lipat",
    "Linggis",
    "Garpu 4 Jari",
    "Belincong",
    "Ganco",
    "Gaetan",
    "Balok Pengaman Selang (Hose Bridge)",
    "Ganjal Ban",
    "Klem Penutup Kebocoran Selang (Hose Bandages)",
    "Alat Pelindung Pernapasan (SCBA)",
    "Mesin Pemotong (Hydraulic Cutter Portable)",
    "Blower",
    "Tangga Manual",
    "Tali",
    "Fire Blanket",
    "Tas/Kotak P3K",
    "Lampu Penerangan Portable",
    "Pengaman Lalu Lintas (Traffic Cone)",
    "Dongrak",
    "Toolkit Unit",
]
BAGIAN_RANSUS = [("I", "Peralatan", [("", "", PERALATAN_RANSUS)])]

RANSUS_BAB, KOMPONEN_RANSUS_BERNOMOR = _diesel_bernomor(BAGIAN_RANSUS)
