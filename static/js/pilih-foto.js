// Every photo input (<input type="file" accept="image/...">) becomes a camera
// button (input.css: .pilih-foto) that tells what was picked: the file's name
// and size, or how many photos. The input itself stays in the form, only out
// of sight, so the browser still sends it, still checks `required` and the
// page's own handlers (previews, kompres-foto.js) still get its change event.
(function () {
  const KAMERA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z"/></svg>';
  const CENTANG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>';

  function ukuran(byte) {
    return byte >= 1048576 ? (byte / 1048576).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(byte / 1024)) + ' KB';
  }

  function perbarui(input) {
    const label = input.closest('.pilih-foto');
    if (!label) return;
    const files = input.files || [];
    const ada = files.length > 0;
    label.classList.toggle('terpilih', ada);
    label.querySelector('.pilih-foto-ikon').innerHTML = ada ? CENTANG : KAMERA;
    // "/ pilih" drops out where the button is narrow (input.css).
    label.querySelector('.pilih-foto-judul').innerHTML = ada ? 'Ganti foto' : 'Ambil<span class="pilih-foto-panjang"> / pilih</span> foto';
    label.querySelector('.pilih-foto-ket').textContent = !ada
      ? (input.multiple ? 'Belum ada foto · bisa lebih dari satu' : 'Belum ada foto dipilih')
      : files.length > 1
        ? `${files.length} foto dipilih · ${ukuran([...files].reduce((n, f) => n + f.size, 0))}`
        : `${files[0].name} · ${ukuran(files[0].size)}`;
  }

  function pasang(input) {
    if (input.closest('.pilih-foto') || input.hasAttribute('data-tanpa-pilih-foto')) return;
    const label = document.createElement('label');
    label.className = 'pilih-foto';
    label.innerHTML = '<span class="pilih-foto-isi"><span class="pilih-foto-ikon"></span><span class="pilih-foto-teks"><span class="pilih-foto-judul"></span><span class="pilih-foto-ket"></span></span></span>';
    input.before(label);
    label.appendChild(input);
    perbarui(input);
  }

  function semua(root) {
    const daftar = root.matches && root.matches('input[type=file]') ? [root] : root.querySelectorAll('input[type=file]');
    for (const input of daftar) {
      if (/image/.test(input.accept || '')) pasang(input);
    }
  }

  // After kompres-foto.js swaps in the smaller files it sends change again: the size shown follows.
  document.addEventListener('change', (e) => {
    if (e.target instanceof HTMLInputElement && e.target.type === 'file') perbarui(e.target);
  });
  // A form reset empties the inputs without a change event.
  document.addEventListener('reset', (e) => setTimeout(() => e.target.querySelectorAll('.pilih-foto input').forEach(perbarui)));
  document.addEventListener('DOMContentLoaded', () => {
    semua(document);
    // Inputs added later, by htmx or by a page's own fetch (the Pemeriksaan
    // checklist after a scan), are fitted as they arrive.
    new MutationObserver((catatan) => {
      for (const c of catatan) {
        for (const n of c.addedNodes) {
          if (n.nodeType === 1 && (n.matches('input[type=file]') || n.querySelector('input[type=file]'))) semua(n);
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  });
})();
