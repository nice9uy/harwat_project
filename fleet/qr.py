import io
from functools import lru_cache
from pathlib import Path

import reportlab
import segno
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

LOGO_PATH = settings.BASE_DIR / "static" / "img" / "kemhan_logo.png"
# Share of the QR width the logo (plus its white backing circle) may cover.
# Error correction level H recovers up to ~30% damaged modules; a centred
# logo at this size hides well under 10%, so scanners still read the code.
LOGO_RATIO = 0.24


# Bold font bundled with ReportLab (already a dependency for the PDFs), so the
# label renders the same with or without system fonts in the container.
LABEL_FONT_PATH = Path(reportlab.__file__).parent / "fonts" / "VeraBd.ttf"


@lru_cache(maxsize=1)
def _logo():
    return Image.open(LOGO_PATH).convert("RGBA")


def _label_font(size):
    try:
        return ImageFont.truetype(str(LABEL_FONT_PATH), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _with_label(qr, label):
    """``qr`` with ``label`` printed centred in a white strip below it."""
    size = qr.width // 12
    font = _label_font(size)
    # Shrink long labels until they fit inside the quiet zone margins.
    while size > 10 and font.getlength(label) > qr.width * 0.9:
        size -= 2
        font = _label_font(size)
    strip = int(size * 1.8)
    out = Image.new("RGBA", (qr.width, qr.height + strip), "white")
    out.alpha_composite(qr, (0, 0))
    # The QR's bottom quiet zone already gives space; pull the text up into it a bit.
    ImageDraw.Draw(out).text(
        (qr.width / 2, qr.height + strip * 0.3), label, font=font, fill="black", anchor="mm",
    )
    return out


def qr_png_with_logo(text, label=None):
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

    if label:
        qr = _with_label(qr, label)

    out = io.BytesIO()
    qr.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
