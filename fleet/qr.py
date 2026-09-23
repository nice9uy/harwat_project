import io
from functools import lru_cache

import segno
from django.conf import settings
from PIL import Image, ImageDraw

LOGO_PATH = settings.BASE_DIR / "static" / "img" / "kemhan_logo.png"
# Share of the QR width the logo (plus its white backing circle) may cover.
# Error correction level H recovers up to ~30% damaged modules; a centred
# logo at this size hides well under 10%, so scanners still read the code.
LOGO_RATIO = 0.24


@lru_cache(maxsize=1)
def _logo():
    return Image.open(LOGO_PATH).convert("RGBA")


def qr_png_with_logo(text):
    buffer = io.BytesIO()
    segno.make(text, error="h", micro=False).save(buffer, kind="png", scale=10, border=2)
    qr = Image.open(io.BytesIO(buffer.getvalue())).convert("RGBA")

    size = int(qr.width * LOGO_RATIO)
    pad = size // 12
    backing = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(backing).ellipse((0, 0, size - 1, size - 1), fill="white")
    logo = _logo().resize((size - 2 * pad, size - 2 * pad), Image.LANCZOS)
    backing.alpha_composite(logo, (pad, pad))

    offset = ((qr.width - size) // 2, (qr.height - size) // 2)
    qr.alpha_composite(backing, offset)

    out = io.BytesIO()
    qr.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
