# core-api

Auth, review logic and FSRS scheduling. Source of truth for business data.

## Commands

```sh
uv sync                  # install dependencies
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check (strict)
uv run uvicorn core_api.main:app --reload
```

## Layout

```
src/core_api/
  api/            routes: parse input, call domain, return output
  domain/         business rules; no HTTP, no SQL
  repositories/   database access; every function takes user_id
  clients/        external services (ai-service, email, storage)
```

## Configuration

Environment variables prefixed with `CORE_` (see `config.py`).

## Sync vs async convention (ADR-0005)

- Routes and database access are **synchronous**: use `def`, not `async def`. FastAPI runs `def` routes in a threadpool, so blocking calls do not stall the event loop.
- Never call blocking code (database, `httpx.Client`, file I/O) inside an `async def`.
- PDF/image processing never runs in a request; it belongs to the `ai-service` worker.
