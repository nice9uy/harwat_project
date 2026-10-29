"""Live notices to open pages over Server-Sent Events (htmx-ext-sse).

A change is announced once (kabarkan) on Valkey's pub/sub channel. Each worker
process holds a single subscription and wakes only its own streams, so the
cost does not grow with the people waiting: an idle stream is a parked
coroutine (a few KB), nothing polls per user, and a stream is only opened by a
page that has something live on it. Without REDIS_URL (tests, a bare
runserver) a notice reaches the streams of the process that made it.

Topics so far: "aktivasi" (the Aktivasi Ketua Tim badge).
"""
import asyncio
import logging
import os

from django.db import transaction

KANAL = "harwat:realtime"
log = logging.getLogger(__name__)

_antrean: set[asyncio.Queue] = set()  # one per open stream of this process
_pendengar: asyncio.Task | None = None  # this process's one subscription
_loop: asyncio.AbstractEventLoop | None = None
_redis = None
_versi: dict[str, int] = {}  # topic -> notices of it this process has had


def _url():
    return os.environ.get("REDIS_URL", "")


def kabarkan(topik):
    """Tell the open pages that ``topik`` changed, once the transaction is in."""
    transaction.on_commit(lambda: _terbitkan(topik))


def _terbitkan(topik):
    global _redis
    if _url():
        try:
            if _redis is None:
                import redis
                _redis = redis.Redis.from_url(_url(), socket_timeout=2, socket_connect_timeout=2)
            _redis.publish(KANAL, topik)
            return
        except Exception:
            log.warning("realtime: kabar %r tidak terkirim lewat Valkey", topik, exc_info=True)
    if _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(_bangunkan, topik)


def versi(topik):
    """How many notices of ``topik`` this process has had: what was worked out
    from the data under an older number is out of date."""
    return _versi.get(topik, 0)


def _bangunkan(topik):
    _versi[topik] = _versi.get(topik, 0) + 1
    for antrean in list(_antrean):
        if not antrean.full():  # a stream far behind loses nothing: it recounts anyway
            antrean.put_nowait(topik)


async def _dengar():
    import redis.asyncio as aredis

    while True:
        try:
            klien = aredis.Redis.from_url(_url())
            async with klien.pubsub() as pubsub:
                await pubsub.subscribe(KANAL)
                async for pesan in pubsub.listen():
                    if pesan["type"] == "message":
                        _bangunkan(pesan["data"].decode())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("realtime: langganan Valkey putus, menyambung lagi", exc_info=True)
            await asyncio.sleep(3)


async def langganan():
    """The topics announced while one stream is open, in order."""
    global _pendengar, _loop
    _loop = asyncio.get_running_loop()
    if _url() and (_pendengar is None or _pendengar.done()):
        _pendengar = _loop.create_task(_dengar())
    antrean = asyncio.Queue(maxsize=8)
    _antrean.add(antrean)
    try:
        while True:
            yield await antrean.get()
    finally:
        _antrean.discard(antrean)


def jumlah_aliran():
    """Streams open in this process (for tests and the load check)."""
    return len(_antrean)
