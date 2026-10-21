"""T1.11: the committed OpenAPI document must match the app.

`packages/api-client` generates its TypeScript types from `openapi.json`. A field changed in
the API without regenerating the client (`just gen-api`) makes this test fail.
"""

from pathlib import Path

from core_api.main import app
from core_api.openapi_export import render_openapi

OPENAPI_JSON = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"


def test_openapi_json_matches_the_app() -> None:
    committed = OPENAPI_JSON.read_text(encoding="utf-8") if OPENAPI_JSON.exists() else ""
    assert committed == render_openapi(app), (
        "packages/api-client/openapi.json is out of date: run `just gen-api`"
    )


def test_render_is_deterministic_json_with_a_final_newline() -> None:
    rendered = render_openapi(app)
    assert rendered == render_openapi(app)
    assert rendered.endswith("}\n")
    assert "\r" not in rendered
