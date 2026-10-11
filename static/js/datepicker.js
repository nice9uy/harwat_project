// Themed calendar for every <input type="date">, instead of the browser's
// own popup (which can't be styled). The input stays a native date input:
// typing a date, `required`, `min` / `max` and the submitted value
// (YYYY-MM-DD) work as before. Touch devices keep their native picker.
(function () {
    if (window.matchMedia("(pointer: coarse)").matches) return;

    var BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
    var HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];
    var panel = null, input = null, tampil = null; // tampil: first day of the month shown

    function iso(d) {
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    }

    function dariIso(s) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
        return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
    }

    function el(tag, kelas, teks) {
        var e = document.createElement(tag);
        if (kelas) e.className = kelas;
        if (teks !== undefined) e.textContent = teks;
        return e;
    }

    function tombol(kelas, teks, label, aksi) {
        var b = el("button", kelas, teks);
        b.type = "button";
        if (label) b.setAttribute("aria-label", label);
        b.addEventListener("click", aksi);
        return b;
    }

    function pilih(nilai) {
        input.value = nilai;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        var i = input;
        tutup();
        i.focus();
    }

    function geser(bulan) {
        tampil = new Date(tampil.getFullYear(), tampil.getMonth() + bulan, 1);
        gambar();
    }

    function gambar() {
        var terpilih = input.value, hariIni = iso(new Date());
        var min = input.min || "", max = input.max || "";
        panel.textContent = "";

        var kepala = el("div", "dp-kepala");
        kepala.appendChild(tombol("dp-nav", "‹", "Bulan sebelumnya", function () { geser(-1); }));
        var judul = el("div", "dp-judul");
        var bulan = el("select", "dp-pilih");
        bulan.setAttribute("aria-label", "Bulan");
        BULAN.forEach(function (nama, i) {
            var o = el("option", "", nama);
            o.value = i;
            bulan.appendChild(o);
        });
        bulan.value = tampil.getMonth();
        bulan.addEventListener("change", function () {
            tampil = new Date(tampil.getFullYear(), +bulan.value, 1);
            gambar();
        });
        var tahun = el("input", "dp-pilih dp-tahun");
        tahun.type = "number";
        tahun.setAttribute("aria-label", "Tahun");
        tahun.value = tampil.getFullYear();
        tahun.addEventListener("change", function () {
            var t = parseInt(tahun.value, 10);
            if (t >= 1900 && t <= 2200) tampil = new Date(t, tampil.getMonth(), 1);
            gambar();
        });
        judul.appendChild(bulan);
        judul.appendChild(tahun);
        kepala.appendChild(judul);
        kepala.appendChild(tombol("dp-nav", "›", "Bulan berikutnya", function () { geser(1); }));
        panel.appendChild(kepala);

        var kisi = el("div", "dp-kisi");
        HARI.forEach(function (h) { kisi.appendChild(el("div", "dp-hari", h)); });
        // Monday first: back up from the 1st to the Monday on or before it.
        var mulai = new Date(tampil.getFullYear(), tampil.getMonth(), 1 - ((tampil.getDay() + 6) % 7));
        for (var i = 0; i < 42; i++) {
            var d = new Date(mulai.getFullYear(), mulai.getMonth(), mulai.getDate() + i);
            var nilai = iso(d);
            var kelas = "dp-tgl";
            if (d.getMonth() !== tampil.getMonth()) kelas += " dp-luar";
            if (nilai === hariIni) kelas += " dp-hari-ini";
            if (nilai === terpilih) kelas += " dp-terpilih";
            var b = tombol(kelas, d.getDate(), d.getDate() + " " + BULAN[d.getMonth()] + " " + d.getFullYear(), pilih.bind(null, nilai));
            if ((min && nilai < min) || (max && nilai > max)) b.disabled = true;
            if (nilai === terpilih) b.setAttribute("aria-current", "date");
            kisi.appendChild(b);
        }
        panel.appendChild(kisi);

        var kaki = el("div", "dp-kaki");
        kaki.appendChild(tombol("dp-teks", "Hapus", null, function () { pilih(""); }));
        var ini = tombol("dp-teks dp-utama", "Hari ini", null, function () { pilih(hariIni); });
        if ((min && hariIni < min) || (max && hariIni > max)) ini.disabled = true;
        kaki.appendChild(ini);
        panel.appendChild(kaki);
    }

    function posisi() {
        if (!panel) return;
        if (!input.isConnected) return tutup();
        var r = input.getBoundingClientRect();
        var tinggi = panel.offsetHeight, lebar = panel.offsetWidth;
        var atas = r.bottom + 6;
        if (atas + tinggi > window.innerHeight - 8 && r.top - 6 - tinggi >= 8) atas = r.top - 6 - tinggi;
        var kiri = Math.max(8, Math.min(r.left, window.innerWidth - lebar - 8));
        panel.style.top = atas + "px";
        panel.style.left = kiri + "px";
    }

    function buka(target) {
        if (panel && input === target) return;
        tutup();
        input = target;
        var awal = dariIso(input.value) || new Date();
        tampil = new Date(awal.getFullYear(), awal.getMonth(), 1);
        panel = el("div", "dp-panel");
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-label", "Pilih tanggal");
        document.body.appendChild(panel);
        gambar();
        posisi();
    }

    function tutup() {
        if (panel) panel.remove();
        panel = input = null;
    }

    function tanggal(e) {
        var t = e.target;
        return t instanceof HTMLInputElement && t.type === "date" && !t.readOnly && !t.disabled ? t : null;
    }

    // A click on the field opens ours; preventDefault keeps the native popup shut.
    document.addEventListener("click", function (e) {
        var t = tanggal(e);
        if (t) {
            e.preventDefault();
            buka(t);
        } else if (panel && !panel.contains(e.target)) {
            tutup();
        }
    });
    // A date typed into the field moves the open calendar to it.
    document.addEventListener("input", function (e) {
        if (panel && e.target === input && e.isTrusted) {
            var d = dariIso(input.value);
            if (d) {
                tampil = new Date(d.getFullYear(), d.getMonth(), 1);
                gambar();
            }
        }
    });
    document.addEventListener("keydown", function (e) {
        if (!panel) return;
        if (e.key === "Escape") {
            e.stopPropagation();
            var i = input;
            tutup();
            i.focus();
        } else if (e.key === "Tab" && e.target === input) {
            tutup();
        } else if (e.key === " " && e.target === input) {
            e.preventDefault(); // Space would open the native popup
        }
    }, true);
    document.addEventListener("keydown", function (e) {
        var t = tanggal(e);
        if (!panel && t && (e.key === " " || (e.altKey && e.key === "ArrowDown"))) {
            e.preventDefault();
            buka(t);
        }
    });
    window.addEventListener("resize", posisi);
    window.addEventListener("scroll", posisi, true);
})();
