"""Serves the uploaded photos (/media/...) from whichever storage holds them
(the disk in development, Garage in production), to signed-in users only."""
import mimetypes

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404


@login_required
def media_view(request, nama):
    # Storage names never climb out of the media root.
    if ".." in nama.split("/") or nama.startswith("/"):
        raise Http404
    try:
        berkas = default_storage.open(nama, "rb")
    except (FileNotFoundError, OSError):
        raise Http404
    except Exception as galat:  # S3: a missing key comes as the client's own error type
        if type(galat).__name__ in ("ClientError", "NoSuchKey"):
            raise Http404
        raise
    response = FileResponse(berkas, content_type=mimetypes.guess_type(nama)[0] or "application/octet-stream")
    # A stored photo never changes (a new upload gets a new name).
    response["Cache-Control"] = "private, max-age=86400"
    return response
