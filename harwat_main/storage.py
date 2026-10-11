"""Storage of the uploaded photos in production: a Garage (S3) bucket."""
from urllib.parse import quote

from storages.backends.s3 import S3Storage


class GarageStorage(S3Storage):
    """S3Storage whose URLs point back at this app (/media/<name>) instead of
    at the bucket: Garage isn't reachable from the browser, and the photos are
    for signed-in users only (accounts.media)."""

    def url(self, name, parameters=None, expire=None, http_method=None):
        return "/media/" + quote(name.lstrip("/"))
