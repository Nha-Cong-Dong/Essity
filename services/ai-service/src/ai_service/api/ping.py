from fastapi import APIRouter

router = APIRouter(prefix="/v1")


# Behind the service-token middleware, unlike /healthz: a 200 here proves the caller's
# token is accepted, not just that the process is up.
@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}
