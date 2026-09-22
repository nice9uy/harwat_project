from django_bolt import BoltAPI, Request

api = BoltAPI()
api.mount_django("/")


@api.get("/api/health")
async def health(request: Request) -> dict:
    return {"status": "ok"}
