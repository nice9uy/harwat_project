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
from django_bolt.serializers import Serializer

api = BoltAPI()

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


@api.post("/auth/login", tags=["auth"])
async def login(request, credentials: LoginCredentials) -> TokenPairResponse:
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
async def refresh(request) -> TokenPairResponse:
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
