// Every button whose action is under way shows a spinner in place of its
// label (input.css: [data-memproses]) and takes no second click, so the user
// sees the app is working: a form's submit button (plain or htmx, also while
// kompres-foto.js is still shrinking its photos) and a button with its own
// hx-get/hx-post (Hapus, Edit, ...). Requests nobody clicked for (polling,
// search-as-you-type) leave the buttons alone. Loaded before kompres-foto.js:
// both listen to submit in the capture phase, and this one must see it first.
(function () {
  const BATAS = 120000; // never spin longer than this (a lost answer)

  function mulai(btn) {
    if (!btn || btn.tagName !== 'BUTTON' || btn.hasAttribute('data-memproses') || btn.hasAttribute('data-tanpa-proses')) return;
    const gaya = getComputedStyle(btn);
    btn.style.setProperty('--warna-proses', gaya.color);
    if (gaya.position === 'static') {
      btn.style.position = 'relative';
      btn.dataset.posisiProses = '1';
    }
    btn.setAttribute('data-memproses', '');
    btn.setAttribute('aria-busy', 'true');
    btn._prosesTimer = setTimeout(() => selesai(btn), BATAS);
  }

  function selesai(btn) {
    if (!btn || !btn.hasAttribute('data-memproses')) return;
    clearTimeout(btn._prosesTimer);
    btn.removeAttribute('data-memproses');
    btn.removeAttribute('aria-busy');
    if (btn.dataset.posisiProses) {
      btn.style.position = '';
      delete btn.dataset.posisiProses;
    }
  }

  // The button that sent ``form``: its submitter, else (a script's
  // requestSubmit(), e.g. Pemeriksaan's "Konfirmasi & Kirim", which is
  // disabled meanwhile and so loses focus) the button last tapped inside it,
  // else its submit button.
  function tombolForm(form, submitter) {
    if (submitter && submitter.tagName === 'BUTTON') return submitter;
    const terakhir = form._tombolTerakhir;
    if (terakhir && form.contains(terakhir)) return terakhir;
    return form.querySelector('button[type=submit]');
  }
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('button');
    if (btn && btn.form) btn.form._tombolTerakhir = btn;
  }, true);

  // htmx: the clicked button, or the submit button of the form being sent.
  document.addEventListener('htmx:beforeRequest', (e) => {
    const pemicu = e.detail.requestConfig && e.detail.requestConfig.triggeringEvent;
    if (!pemicu || (pemicu.type !== 'click' && pemicu.type !== 'submit')) return;
    const elt = e.detail.elt;
    const btn = elt.tagName === 'FORM' ? tombolForm(elt, pemicu.submitter) : elt.closest('button');
    if (!btn) return;
    mulai(btn);
    e.detail.elt._tombolProses = btn;
  });
  ['htmx:afterRequest', 'htmx:sendError', 'htmx:timeout', 'htmx:abort'].forEach((nama) =>
    document.addEventListener(nama, (e) => {
      const elt = e.detail.elt;
      if (elt && elt._tombolProses) {
        selesai(elt._tombolProses);
        delete elt._tombolProses;
      }
    }));

  // A form submitted (after the browser's own validation): plain forms leave
  // the page; htmx forms are handled above; a submit some script cancels for
  // good (not htmx, not waiting for its photos) gets its button back.
  document.addEventListener('submit', (e) => {
    const form = e.target;
    const btn = tombolForm(form, e.submitter);
    if (!btn) return;
    mulai(btn);
    setTimeout(() => {
      if (e.defaultPrevented && !form.classList.contains('htmx-request') && !form.dataset.kirimSetelahKompres && !form._tombolProses) {
        selesai(btn);
      }
    }, 0);
  }, true);

  // Back to a page kept in the browser's cache: nothing is under way there.
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('[data-memproses]').forEach(selesai);
  });
})();
