// Shrinks every photo picked in an <input type="file" accept="image/*">
// before it is uploaded: at most MAX_SIDE px on the long side, re-encoded as
// JPEG. A 5-10 MB phone photo becomes a few hundred KB, so forms with many
// photos send quickly on a slow connection. The server compresses again
// (fleet/images.py) in case this script didn't run.
(function () {
    var MAX_SIDE = 1600, KUALITAS = 0.75;
    var sedang = new WeakMap(); // form -> number of inputs still compressing

    function kompres(file) {
        if (!/^image\//.test(file.type) || file.type === "image/gif") return Promise.resolve(file);
        return createImageBitmap(file, { imageOrientation: "from-image" }).then(function (gambar) {
            var skala = Math.min(1, MAX_SIDE / Math.max(gambar.width, gambar.height));
            var kanvas = document.createElement("canvas");
            kanvas.width = Math.round(gambar.width * skala);
            kanvas.height = Math.round(gambar.height * skala);
            var ctx = kanvas.getContext("2d");
            ctx.fillStyle = "#fff"; // transparent PNGs get a white background
            ctx.fillRect(0, 0, kanvas.width, kanvas.height);
            ctx.drawImage(gambar, 0, 0, kanvas.width, kanvas.height);
            gambar.close();
            return new Promise(function (selesai) { kanvas.toBlob(selesai, "image/jpeg", KUALITAS); });
        }).then(function (blob) {
            // Keep the original when it is already the smaller one, but only
            // in a format the server is sure to read (a small HEIC or AVIF
            // would be refused there as "bukan gambar yang valid").
            var terbaca = /^image\/(jpeg|png)$/.test(file.type);
            if (!blob || (blob.size >= file.size && terbaca)) return file;
            var nama = file.name.replace(/\.[^.]*$/, "") + ".jpg";
            return new File([blob], nama, { type: "image/jpeg", lastModified: file.lastModified });
        }).catch(function () {
            return file; // not decodable here: send as is, the server decides
        });
    }

    function hitung(form, selisih) {
        if (!form) return;
        var n = (sedang.get(form) || 0) + selisih;
        sedang.set(form, n);
        // Lets the page show that the photo is still being shrunk.
        if (n > 0) form.dataset.memprosesFoto = "";
        else delete form.dataset.memprosesFoto;
        if (n === 0 && form.dataset.kirimSetelahKompres) {
            delete form.dataset.kirimSetelahKompres;
            // requestSubmit is missing before iOS 16; clicking the submit button
            // validates and submits the same way.
            if (form.requestSubmit) form.requestSubmit();
            else (form.querySelector('[type="submit"]') || form).click();
        }
    }

    // Capture phase, so the page's own change handlers (photo previews) only
    // see the change event re-sent below, once the files are the small ones.
    document.addEventListener("change", function (e) {
        var input = e.target;
        if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
        if (!/image/.test(input.accept || "") || e.sudahDikompres || !input.files.length) return;
        if (!window.createImageBitmap || !window.DataTransfer) return;
        e.stopPropagation();
        var form = input.form;
        hitung(form, 1);
        Promise.all(Array.prototype.map.call(input.files, kompres)).then(function (files) {
            var dt = new DataTransfer();
            files.forEach(function (f) { dt.items.add(f); });
            input.files = dt.files;
        }).finally(function () {
            var ulang = new Event("change", { bubbles: true });
            ulang.sudahDikompres = true;
            input.dispatchEvent(ulang);
            hitung(form, -1);
        });
    }, true);

    // Simpan pressed while photos are still being shrunk: send once they are done.
    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (sedang.get(form) > 0) {
            e.preventDefault();
            e.stopPropagation();
            form.dataset.kirimSetelahKompres = "1";
        }
    }, true);
})();
