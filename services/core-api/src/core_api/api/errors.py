"""Error responses that never carry the caller's input back (ADR-0013).

FastAPI's default 422 includes each invalid field's `input`, and the whole body when a field is
missing: a password would travel back to web, and from there into any log that records
upstream errors. Only where and what kind of error remains.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def install_validation_handler(app: FastAPI) -> None:
    async def invalid_request(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [
            {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    app.add_exception_handler(RequestValidationError, invalid_request)
