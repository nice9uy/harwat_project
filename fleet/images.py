import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_SIDE = 1600
JPEG_QUALITY = 75


def compress_photo(upload):
    """Shrink an uploaded photo to at most MAX_SIDE px and re-encode as JPEG.

    Phone photos are often 3-10 MB; this typically brings them to a few
    hundred KB. EXIF orientation is applied first so portrait shots stay
    upright once the metadata is dropped.
    """
    upload.seek(0)
    with Image.open(upload) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        if img.mode != "RGB":
            background = Image.new("RGB", img.size, "white")
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return ContentFile(out.getvalue(), name=f"{Path(upload.name).stem}.jpg")
