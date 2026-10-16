import httpx2

from core_api.config import Settings
from core_api.logging import REQUEST_ID_HEADER, request_id_var

SERVICE_TOKEN_HEADER = "X-Service-Token"


class AiServiceUnavailableError(Exception):
    """ai-service did not answer, timed out, or answered with an error status."""


class AiServiceClient:
    """Synchronous client for ai-service (ADR-0005: core-api routes are sync)."""

    def __init__(self, http: httpx2.Client) -> None:
        self._http = http

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx2.BaseTransport | None = None
    ) -> "AiServiceClient":
        http = httpx2.Client(
            base_url=settings.ai_service_url,
            headers={SERVICE_TOKEN_HEADER: settings.ai_service_token.get_secret_value()},
            timeout=settings.ai_service_timeout_seconds,
            transport=transport,
            event_hooks={"request": [_forward_request_id]},
        )
        return cls(http)

    def ping(self) -> None:
        try:
            response = self._http.get("/v1/ping")
            response.raise_for_status()
        except httpx2.HTTPError as exc:
            raise AiServiceUnavailableError(str(exc)) from exc

    def close(self) -> None:
        self._http.close()


def _forward_request_id(request: httpx2.Request) -> None:
    # Same id on both sides, so one user request can be followed across services.
    request_id = request_id_var.get()
    if request_id is not None:
        request.headers[REQUEST_ID_HEADER] = request_id
