from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from core_api.clients.ai_client import AiServiceClient, AiServiceUnavailableError

router = APIRouter(prefix="/v1")

ServiceStatus = Literal["ok", "unavailable"]


class PingResponse(BaseModel):
    core_api: ServiceStatus
    ai_service: ServiceStatus


def get_ai_client(request: Request) -> AiServiceClient:
    return cast(AiServiceClient, request.app.state.ai_client)


@router.get("/ping")
def ping(
    response: Response, ai_client: Annotated[AiServiceClient, Depends(get_ai_client)]
) -> PingResponse:
    try:
        ai_client.ping()
    except AiServiceUnavailableError:
        response.status_code = 503
        return PingResponse(core_api="ok", ai_service="unavailable")
    return PingResponse(core_api="ok", ai_service="ok")
