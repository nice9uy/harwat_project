from typing import Annotated

from django.conf import settings
from django.contrib.auth import aauthenticate

from django_bolt import BoltAPI
from django_bolt.auth import (
    DjangoORMRevocation,
    IsAuthenticated,
    JWTAuthentication,
    LoginCredentials,
    TokenRotationError,
    create_token_pair,
    rotate_refresh_token,
)
from django_bolt.exceptions import HTTPException
from django_bolt.middleware import rate_limit
from django_bolt.serializers import Serializer

api = BoltAPI()

from django_bolt.param_functions import Cookie, Header  # noqa: E402

from .keamanan import tolak_bila_diblokir  # noqa: E402

revocation_store = DjangoORMRevocation(model="accounts.RevokedToken")

refresh_auth = JWTAuthentication(
    secret=settings.SECRET_KEY,
    token_type="refresh",
    revocation_store=revocation_store,
)


class TokenPairResponse(Serializer):
    access_token: str
    refresh_token: str
    token_type: str


class DetailResponse(Serializer):
    detail: str


# Password guessing is slowed down: a few tries a second per address.
@api.post("/auth/login", tags=["auth"])
@rate_limit(rps=2, burst=10, key="ip")
async def login(request, credentials: LoginCredentials, x_real_ip: Annotated[str | None, Header(alias="x-real-ip")] = None) -> TokenPairResponse:
    # These Bolt routes don't pass Django's middleware: the blacklist is checked here.
    await tolak_bila_diblokir(x_real_ip)
    user = await aauthenticate(username=credentials.username, password=credentials.password)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    pair = create_token_pair(user, secret=settings.SECRET_KEY, method="pwd")
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
    }


@api.post("/auth/refresh", auth=[refresh_auth], guards=[IsAuthenticated()], tags=["auth"])
async def refresh(request, x_real_ip: Annotated[str | None, Header(alias="x-real-ip")] = None) -> TokenPairResponse:
    await tolak_bila_diblokir(x_real_ip)
    try:
        pair = await rotate_refresh_token(
            request["context"]["auth_claims"],
            store=revocation_store,
            secret=settings.SECRET_KEY,
        )
    except TokenRotationError:
        raise HTTPException(status_code=401, detail="Invalid or reused refresh token")
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
    }


@api.post("/auth/logout", auth=[refresh_auth], guards=[IsAuthenticated()], tags=["auth"])
async def logout(request) -> DetailResponse:
    claims = request["context"]["auth_claims"]
    await revocation_store.revoke(claims["jti"], exp=claims.get("exp"))
    if claims.get("fam"):
        await revocation_store.revoke_family(claims["fam"], exp=claims.get("exp"))
    return {"detail": "Logged out"}


# --- Live notices (Server-Sent Events, see accounts/realtime.py) -----------

# A stream ends after this long and the page opens a new one, which checks
# its user again (signed out, switched off, role taken away).
UMUR_ALIRAN = 30 * 60


async def _pengguna_sesi(kunci):
    """The signed-in user of the app's session cookie (its value: ``kunci``), or None."""
    from importlib import import_module

    from django.contrib.auth import aget_user

    if not kunci:
        return None

    class _Permintaan:
        session = import_module(settings.SESSION_ENGINE).SessionStore(kunci)

    user = await aget_user(_Permintaan())
    return user if user.is_authenticated else None


def _render_lencana(matra):
    from django.template.loader import render_to_string

    from .aktivasi import jumlah_menunggu_matra

    return render_to_string("_lencana_jumlah.html", {"jumlah": jumlah_menunggu_matra(matra)})


# One count per matra for all the streams of this process: a notice wakes
# every stream, and they share the answer worked out after it (realtime.versi)
# instead of each asking the database.
_lencana_terakhir: dict[str, tuple[int, str]] = {}
_lencana_kunci: dict[str, "asyncio.Lock"] = {}


async def _lencana_bersama(matra):
    import asyncio

    from asgiref.sync import sync_to_async

    from . import realtime

    kunci = _lencana_kunci.setdefault(matra, asyncio.Lock())
    async with kunci:
        versi = realtime.versi("aktivasi")
        dihitung, html = _lencana_terakhir.get(matra, (-1, ""))
        if dihitung != versi:
            html = await sync_to_async(_render_lencana)(matra)
            _lencana_terakhir[matra] = (versi, html)
    return html


@api.get("/sse/aktivasi", tags=["realtime"])
async def sse_aktivasi(
    request,
    # Bolt hands a route only the headers and cookies it declares.
    x_real_ip: Annotated[str | None, Header(alias="x-real-ip")] = None,
    sesi: Annotated[str | None, Cookie(alias=settings.SESSION_COOKIE_NAME)] = None,
):
    """The Aktivasi Ketua Tim badge, live: its count now, then again on every
    sign-up, activation or deletion of a Ketua Tim."""
    import asyncio

    from asgiref.sync import sync_to_async
    from django_bolt import EventSourceResponse, ServerSentEvent

    from . import realtime, roles

    from .aktivasi import _matra_admin

    await tolak_bila_diblokir(x_real_ip)
    user = await _pengguna_sesi(sesi)
    if user is None or "aktivasi_ketua_tim" not in await sync_to_async(roles.allowed_menus)(user):
        raise HTTPException(status_code=403, detail="Forbidden")
    # A superuser's open Hacking Activity page refreshes on every new event.
    superuser = user.is_superuser
    matra = await sync_to_async(_matra_admin)(user)  # "" for a superuser: every matra

    async def aliran():
        yield ServerSentEvent(raw_data=await _lencana_bersama(matra), event="aktivasi", retry=5000)
        try:
            async with asyncio.timeout(UMUR_ALIRAN):
                async for topik in realtime.langganan():
                    if topik == "aktivasi":
                        yield ServerSentEvent(raw_data=await _lencana_bersama(matra), event="aktivasi")
                    elif topik == "keamanan" and superuser:
                        yield ServerSentEvent(raw_data="1", event="keamanan")
        except TimeoutError:
            return

    # Proxies must pass the events on at once (nginx: X-Accel-Buffering).
    return EventSourceResponse(aliran(), ping_interval=25, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
