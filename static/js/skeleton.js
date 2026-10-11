// Skeleton rows for every table while its data loads: when a request (HTMX,
// a boosted or a plain page navigation) takes longer than TUNDA ms, the
// cells of the tables it will replace turn into shimmering bars; a target
// without a table (a modal body waiting for its content) gets a skeleton
// table of its own. The response swaps the real rows in.
(function () {
  const TUNDA = 300; // faster answers show no skeleton at all
  const BATAS = 15000; // a navigation that never replaces the page (a download) gives up
  const BARIS = 5;
  const menunggu = new WeakMap(); // request target -> its timer

  function tabelDi(el) {
    const tabel = [...el.querySelectorAll('table')];
    if (el.matches && el.matches('table')) tabel.push(el);
    else if (el.closest && !tabel.length) {
      // A target inside a table (a row, a tbody): that table.
      const induk = el.closest('table');
      if (induk) tabel.push(induk);
    }
    return tabel;
  }

  function kerangka(kolom) {
    const tabel = document.createElement('table');
    tabel.className = 'kerangka-tabel w-full text-sm';
    const tbody = tabel.createTBody();
    for (let b = 0; b < BARIS; b++) {
      const tr = tbody.insertRow();
      for (let k = 0; k < kolom; k++) tr.insertCell().innerHTML = '&nbsp;';
    }
    return tabel;
  }

  function pasang(el) {
    const tabel = tabelDi(el);
    tabel.forEach((t) => {
      t.classList.add('memuat');
      // An empty table still shows rows to come.
      const tbody = t.tBodies[0];
      const kolom = t.tHead && t.tHead.rows[0] ? t.tHead.rows[0].cells.length : 0;
      if (tbody && kolom && !tbody.querySelector('td:not([colspan])')) {
        const sisipan = kerangka(kolom).tBodies[0];
        sisipan.dataset.kerangka = '1';
        tbody.hidden = true;
        tbody.after(sisipan);
      }
    });
    // A modal body (or any small target) with nothing in it yet.
    if (!tabel.length && el !== document.body && el.tagName !== 'MAIN' && el.children.length <= 1 && el.textContent.trim().length < 20) {
      el.dataset.kerangkaAsli = el.innerHTML;
      el.replaceChildren(Object.assign(kerangka(4), { className: 'kerangka-tabel memuat w-full text-sm' }));
    }
  }

  function lepas(el) {
    if (!el || !el.querySelectorAll) return;
    el.querySelectorAll('tbody[data-kerangka]').forEach((t) => {
      if (t.previousElementSibling) t.previousElementSibling.hidden = false;
      t.remove();
    });
    el.querySelectorAll('table.memuat').forEach((t) => t.classList.remove('memuat'));
    if (el.matches && el.matches('table.memuat')) el.classList.remove('memuat');
    if (el.dataset && el.dataset.kerangkaAsli !== undefined) {
      if (el.querySelector('.kerangka-tabel')) el.innerHTML = el.dataset.kerangkaAsli;
      delete el.dataset.kerangkaAsli;
    }
  }

  function sasaran(target) {
    // A boosted navigation swaps the whole body: only the page's own tables matter.
    return target === document.body ? document.querySelector('main') || target : target;
  }

  document.addEventListener('htmx:beforeRequest', (e) => {
    const pemicu = e.detail.elt;
    // A table refreshing itself on a timer keeps its rows meanwhile.
    if (pemicu && /every/.test(pemicu.getAttribute('hx-trigger') || '')) return;
    const el = sasaran(e.detail.target);
    if (!el) return;
    clearTimeout(menunggu.get(el));
    menunggu.set(el, setTimeout(() => pasang(el), TUNDA));
  });
  const selesai = (e) => {
    const el = sasaran(e.detail.target);
    if (!el) return;
    clearTimeout(menunggu.get(el));
    // A swap brought the real rows; an error or an empty answer leaves the old ones.
    lepas(el);
    lepas(el.closest && el.closest('table') ? el.closest('table').parentElement : null);
  };
  ['htmx:afterRequest', 'htmx:afterSwap', 'htmx:sendError', 'htmx:responseError', 'htmx:timeout'].forEach((nama) =>
    document.addEventListener(nama, selesai));

  // Plain navigations (links and GET forms outside hx-boost): the page stays
  // on screen until the next one arrives.
  let navigasi = null;
  function mulaiNavigasi() {
    const main = document.querySelector('main');
    if (!main) return;
    clearTimeout(navigasi);
    navigasi = setTimeout(() => {
      pasang(main);
      navigasi = setTimeout(() => lepas(main), BATAS);
    }, TUNDA);
  }
  const UNDUHAN = /unduh|export|ekspor|\/pdf\/|\.pdf|\.xlsx|\.docx|\.conf/i;
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey) return;
    if (a.target === '_blank' || a.hasAttribute('download') || a.origin !== location.origin) return;
    const href = a.getAttribute('href');
    if (href.startsWith('#') || href.startsWith('javascript:') || UNDUHAN.test(href)) return;
    // HTMX handles boosted links itself (htmx:beforeRequest above).
    if (a.closest('[hx-boost=true]') && a.getAttribute('hx-boost') !== 'false') return;
    if (a.hasAttribute('hx-get')) return;
    mulaiNavigasi();
  });
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (e.defaultPrevented || (form.method || 'get').toLowerCase() !== 'get') return;
    if (form.hasAttribute('hx-get') || form.target === '_blank') return;
    mulaiNavigasi();
  });
  // Back/forward restores the page as it was left: without the skeleton.
  window.addEventListener('pageshow', () => {
    clearTimeout(navigasi);
    lepas(document.querySelector('main'));
  });
})();
