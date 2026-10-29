// The app as an icon on the home screen (accounts/pwa.py): registers the
// pass-through service worker the browser wants before it offers to install,
// and keeps the browser's install offer for the Shortcut page's button.
(function () {
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {}));
  }
  window.harwatPasang = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();  // shown from the Shortcut page's button instead
    window.harwatPasang = e;
    document.dispatchEvent(new CustomEvent('harwat-bisa-dipasang'));
  });
  window.addEventListener('appinstalled', () => {
    window.harwatPasang = null;
    document.dispatchEvent(new CustomEvent('harwat-terpasang'));
  });
})();
