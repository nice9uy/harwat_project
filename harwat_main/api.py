from django_bolt import BoltAPI, Request
from django_bolt.openapi import OpenAPIConfig, ScalarRenderPlugin

api = BoltAPI(
    openapi_config=OpenAPIConfig(
        title="BMN Harwat API",
        version="1.0.0",
        path="/api/docs",
        render_plugins=[ScalarRenderPlugin(path="/")],
    )
)
api.mount_django("/")


@api.get("/api/health")
async def health(request: Request) -> dict:
    return {"status": "ok"}
