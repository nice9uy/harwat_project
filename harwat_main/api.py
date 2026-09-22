from django_bolt import BoltAPI, Request

api = BoltAPI()


@api.get("/api/health")
async def health(request: Request) -> dict:
    return {"status": "ok"}
