// Shared camera QR scanner (html5-qrcode) for pages that scan vehicle QR
// codes. The library is ~370 KB, so it is only fetched on first use.
(function () {
    var libPromise = null;

    function loadLib(src) {
        if (window.Html5Qrcode) return Promise.resolve();
        if (!libPromise) {
            libPromise = new Promise(function (resolve, reject) {
                var s = document.createElement('script');
                s.src = src;
                s.onload = resolve;
                s.onerror = function () {
                    libPromise = null;
                    reject('pemindai gagal dimuat');
                };
                document.head.appendChild(s);
            });
        }
        return libPromise;
    }

    window.bmnQrScanner = function (libSrc) {
        var scanner = null;
        return {
            start: async function (elementId, onText) {
                // Browsers hand out the camera to secure pages only (HTTPS or
                // localhost): over plain HTTP the library can only say
                // "Camera streaming not supported by the browser".
                if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                    throw 'halaman ini dibuka lewat HTTP. Kamera hanya bisa dipakai lewat HTTPS — buka '
                        + 'https://' + location.hostname + ':8443' + location.pathname + ' (port HTTPS aplikasi).';
                }
                await loadLib(libSrc);
                scanner = new window.Html5Qrcode(elementId);
                await scanner.start(
                    { facingMode: 'environment' },
                    { fps: 10, qrbox: { width: 240, height: 240 } },
                    onText,
                    function () {}
                );
            },
            stop: async function () {
                var s = scanner;
                scanner = null;
                if (!s) return;
                try {
                    if (s.isScanning) await s.stop();
                    s.clear();
                } catch (err) {}
            },
        };
    };

    // Vehicle QR text is "No. Registrasi: <nopol>\n..."; returns the nopol or null.
    window.bmnNopolFromQr = function (text) {
        var line = text.split('\n').find(function (l) { return l.indexOf('No. Registrasi:') === 0; });
        return line ? line.slice(line.indexOf(':') + 1).trim() : null;
    };
})();
