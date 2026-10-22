"""R30 (plan D2): core-api is internal; its docs and schema are never served, in any environment.

The schema the web client is built from comes from `app.openapi()` (scripts/openapi_export.py),
which does not need the route.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_r30_docs_and_openapi_are_always_off(client: TestClient, path: str) -> None:
    # Red when: FastAPI(...) keeps its default docs_url, redoc_url or openapi_url.
    assert client.get(path).status_code == 404
