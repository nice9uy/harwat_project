// Alpine component: a text field whose suggestion list opens once the user
// types (not on focus) and that stores
// the chosen option's value in a hidden input (used for Satuan / Kesatuan).
// Options come from a <script type="application/json"> tag ({v, l} objects).
document.addEventListener('alpine:init', function () {
    window.Alpine.data('autocomplete', function (opsiId, nilaiAwal, wajib, namaData) {
        return {
            opsi: [],
            q: '',
            nilai: '',
            buka: false,
            aktif: 0,
            init: function () {
                var el = document.getElementById(opsiId);
                this.opsi = el ? JSON.parse(el.textContent) : [];
                var awal = this.opsi.find(function (o) { return String(o.v) === String(nilaiAwal); });
                if (awal) { this.nilai = String(awal.v); this.q = awal.l; }
                this.$nextTick(this.cekValid.bind(this));
            },
            get hasil() {
                var q = this.q.trim().toLowerCase();
                var cocok = q ? this.opsi.filter(function (o) { return o.l.toLowerCase().indexOf(q) !== -1; }) : this.opsi;
                return cocok.slice(0, 50);
            },
            ketik: function () {
                this.buka = this.q.trim() !== '';
                this.aktif = 0;
                var q = this.q.trim().toLowerCase();
                var persis = this.opsi.find(function (o) { return o.l.toLowerCase() === q; });
                this.nilai = persis ? String(persis.v) : '';
                this.cekValid();
            },
            pilih: function (o) {
                this.nilai = String(o.v);
                this.q = o.l;
                this.buka = false;
                this.cekValid();
            },
            kosongkan: function () {
                this.q = '';
                this.nilai = '';
                this.cekValid();
                this.$refs.teks.focus();
            },
            turun: function () {
                if (!this.q.trim()) return;
                this.buka = true;
                this.aktif = Math.min(this.aktif + 1, this.hasil.length - 1);
            },
            naik: function () { this.aktif = Math.max(this.aktif - 1, 0); },
            enter: function (e) {
                if (this.buka && this.hasil[this.aktif]) { e.preventDefault(); this.pilih(this.hasil[this.aktif]); }
            },
            cekValid: function () {
                var pesan = '';
                if (!this.nilai && this.q.trim()) pesan = 'Pilih ' + namaData + ' dari daftar.';
                else if (!this.nilai && wajib) pesan = 'Pilih ' + namaData + '.';
                this.$refs.teks.setCustomValidity(pesan);
            },
        };
    });
});
