"""core-api's OpenAPI document, as committed in `packages/api-client/openapi.json` (T1.11).

`python -m core_api.openapi_export <path>` writes it; `just gen-api` runs that, then
regenerates the TypeScript types.
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI


def render_openapi(app: FastAPI) -> str:
    """Sorted keys, two-space indent and a final newline, so the file only changes when the
    API does and the diff reads well in review."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> None:
    from core_api.main import app

    (target,) = argv
    Path(target).write_text(render_openapi(app), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1:])
