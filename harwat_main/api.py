from django_bolt import BoltAPI, Request
from django_bolt.openapi import OpenAPIConfig, ScalarRenderPlugin

from accounts.middleware import superuser_only

api = BoltAPI(
    openapi_config=OpenAPIConfig(
        title="BMN Harwat API",
        version="1.0.0",
        path="/api/docs",
        render_plugins=[ScalarRenderPlugin(path="/")],
        # Superusers only (signed in through the app); anyone else gets a 404.
        django_auth=superuser_only,
    )
)
api.mount_django("/")


@api.get("/api/health")
async def health(request: Request) -> dict:
    return {"status": "ok"}
