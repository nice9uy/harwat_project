// When the server is busy (templates/_server_sibuk.html):
// - a request someone clicked for that is still waiting after ANTREAN_MS shows
//   "Server sedang sibuk… dalam antrean" at the top until it is answered;
// - a request that failed (5xx, 429, timeout, no connection) opens a dialog
//   whose "Coba lagi" sends the same request again. htmx leaves the page as it
//   was on an error, so whatever was typed or picked (photos too) is still
//   there and nothing has to be filled in again.
// So that a full-page form (Pemeriksaan, Perbaikan, Ganti Password, the
// confirm dialogs...) gets the same, the POST forms in <main> are sent through
// htmx too (boosted): a failed one no longer leaves the page for an error page.
(function () {
  const ANTREAN_MS = 2500;
  let menunggu = 0;
  let timer = null;
  let ulangi = null;

  const el = (id) => document.getElementById(id);

  function antrean(tampil) {
    const t = el('antrean-sibuk');
    if (t) t.hidden = !tampil;
  }

  function diklik(detail) {
    const pemicu = detail.requestConfig && detail.requestConfig.triggeringEvent;
    return pemicu && (pemicu.type === 'click' || pemicu.type === 'submit');
  }

  function caraUlang(detail) {
    const elt = detail.elt;
    const pemicu = detail.requestConfig && detail.requestConfig.triggeringEvent;
    if (elt.tagName === 'FORM') {
      const pengirim = pemicu && pemicu.submitter;
      return () => (pengirim && elt.contains(pengirim) ? elt.requestSubmit(pengirim) : elt.requestSubmit());
    }
    return () => htmx.trigger(elt, (pemicu && pemicu.type) || 'click');
  }

  function bukaDialog(keterangan, fn) {
    const m = el('server-sibuk');
    if (!m) return;
    ulangi = fn;
    m.querySelector('[data-sibuk-detail]').textContent = keterangan;
    m.hidden = false;
    m.querySelector('[data-sibuk-ulang]').focus();
  }

  function tutupDialog() {
    const m = el('server-sibuk');
    if (m) m.hidden = true;
    ulangi = null;
  }

  document.addEventListener('htmx:beforeRequest', (e) => {
    if (!diklik(e.detail)) return;
    e.detail.elt._ditunggu = true;
    if (++menunggu === 1) timer = setTimeout(() => antrean(true), ANTREAN_MS);
  });
  document.addEventListener('htmx:afterRequest', (e) => {
    if (!e.detail.elt._ditunggu) return;
    delete e.detail.elt._ditunggu;
    if (--menunggu <= 0) {
      menunggu = 0;
      clearTimeout(timer);
      antrean(false);
    }
  });

  function gagal(e, keterangan) {
    if (!diklik(e.detail)) return;
    bukaDialog(keterangan, caraUlang(e.detail));
  }
  document.addEventListener('htmx:responseError', (e) => {
    const kode = e.detail.xhr.status;
    if (kode >= 500 || kode === 429) gagal(e, kode === 504 ? 'Waktu tunggu habis (504)' : `Kode ${kode}`);
  });
  document.addEventListener('htmx:sendError', (e) => gagal(e, 'Koneksi ke server terputus'));
  document.addEventListener('htmx:timeout', (e) => gagal(e, 'Waktu tunggu habis'));

  document.addEventListener('click', (e) => {
    if (e.target.closest('[data-sibuk-ulang]')) {
      const fn = ulangi;
      tutupDialog();
      if (fn) fn();
    } else if (e.target.closest('[data-sibuk-tutup]') || e.target.id === 'server-sibuk') {
      tutupDialog();
    }
  });
  document.addEventListener('keydown', (e) => {
    const m = el('server-sibuk');
    if (e.key === 'Escape' && m && !m.hidden) {
      e.stopImmediatePropagation();
      tutupDialog();
    }
  }, true);

  // The full-page POST forms of <main>, boosted (see above). Not: forms htmx
  // already sends, ones opening elsewhere (target) or marked data-tanpa-ajax.
  function boost(root) {
    const main = document.querySelector('main');
    if (!main || !window.htmx) return;
    const forms = root.matches && root.matches('form') ? [root] : root.querySelectorAll('form');
    for (const form of forms) {
      if (!main.contains(form) || (form.getAttribute('method') || '').toLowerCase() !== 'post') continue;
      if (form.hasAttribute('hx-post') || form.hasAttribute('hx-boost') || form.target || form.hasAttribute('data-tanpa-ajax')) continue;
      form.setAttribute('hx-boost', 'true');
      htmx.process(form);
    }
  }
  document.addEventListener('htmx:load', (e) => boost(e.detail.elt));
  document.addEventListener('DOMContentLoaded', () => boost(document));
})();
