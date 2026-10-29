"""The app as an icon on a phone's home screen (a Progressive Web App), and
clearing what the browser keeps of it.

- /manifest.webmanifest: name, icons, colours, opening full screen (standalone).
- /sw.js: a service worker that only passes requests through. Browsers want one
  before they offer to install; it caches nothing, so the app never shows an
  out-of-date page. Served from the root so that it covers every page.
- Shortcut (menu): the install button where the browser offers one, else how
  to add the icon by hand, per phone.
- Hapus Cache (menu): empties this device's caches for the app, then reloads.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST


@cache_control(max_age=3600)
def manifest_view(request):
    data = {
        "name": "Harwat — Pemeliharaan dan Perawatan",
        "short_name": "Harwat",
        "description": "Pemeriksaan, perbaikan dan riwayat kendaraan dan non kendaraan.",
        "id": "/",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "lang": "id",
        "background_color": "#0B1F3A",
        "theme_color": "#0B1F3A",
        "icons": [
            {"src": static("img/ikon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("img/ikon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("img/ikon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/manifest+json")


SERVICE_WORKER = """// Harwat: makes the app installable on a home screen. Caches nothing: every
// request goes to the network as usual, so no page is ever out of date.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


@cache_control(no_cache=True)
def service_worker_view(request):
    response = HttpResponse(SERVICE_WORKER, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response


@login_required
def shortcut_view(request):
    return render(request, "accounts/shortcut.html")


@login_required
def hapus_cache_view(request):
    return render(request, "accounts/hapus_cache.html")


@login_required
@require_POST
def hapus_cache_server_view(request):
    """Asks the browser to drop its HTTP cache of the app (Clear-Site-Data;
    honoured over HTTPS). The page empties the rest itself."""
    response = HttpResponse(status=204)
    response["Clear-Site-Data"] = '"cache"'
    return response
