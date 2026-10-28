// A modal opened together with the request that fills it (@click="modalOpen = true"
// plus hx-get into #...-modal-body) stays invisible until its content has
// arrived, then fades in: no flash of the previous modal's content or of an
// empty box first. A slow answer shows the modal after TUNDA ms anyway, with
// skeleton.js's loading rows in it. A modal already open (a form inside it
// posting back into it) is left as it is.
(function () {
  const TUNDA = 400;
  const menunggu = new WeakMap(); // modal overlay -> its reveal timer

  function lapisan(target) {
    if (!target || !target.id || !/modal-body$/.test(target.id)) return null;
    return target.closest('.fixed');
  }

  function tampilkan(el) {
    clearTimeout(menunggu.get(el));
    menunggu.delete(el);
    el.style.transition = 'opacity 150ms ease-out';
    el.style.opacity = '1';
  }

  document.addEventListener('htmx:beforeRequest', (e) => {
    const el = lapisan(e.detail.target);
    // Alpine shows the modal a tick after the click, so a modal being opened
    // now is still display:none here.
    if (!el || getComputedStyle(el).display !== 'none') return;
    el.style.transition = 'none';
    el.style.opacity = '0';
    // The previous modal's content must not show while this one loads.
    e.detail.target.replaceChildren();
    clearTimeout(menunggu.get(el));
    menunggu.set(el, setTimeout(() => tampilkan(el), TUNDA));
  });

  ['htmx:afterSettle', 'htmx:responseError', 'htmx:sendError', 'htmx:timeout'].forEach((nama) =>
    document.addEventListener(nama, (e) => {
      const el = lapisan(e.detail.target);
      if (el && menunggu.has(el)) tampilkan(el);
    }));
})();
