# core-api

Auth, review logic and FSRS scheduling. Source of truth for business data.

## Commands

```sh
uv sync                  # install dependencies
uv run pytest            # tests (needs PostgreSQL: `just up` from the repo root)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check (strict)
uv run uvicorn core_api.main:app --reload
uv run alembic upgrade head                                   # apply migrations
uv run alembic revision --autogenerate --rev-id 0002 -m "..."  # new migration
uv run alembic check                                          # models match migrations
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

Environment variables prefixed with `CORE_` (see `config.py`). Required, or core-api does not start:

- `CORE_DATABASE_URL`: `postgresql+psycopg://user:password@host:5432/core`. Migrations need only this one.
- `CORE_AI_SERVICE_TOKEN`: at least 32 characters, same value as `AI_SERVICE_TOKEN` in ai-service.

Tests use `CORE_TEST_DATABASE_URL` (default: the Compose Postgres, database `core_test`). Each test runs in a transaction that is rolled back, and tests run in random order (`pytest-randomly`).

## Database

- SQLAlchemy 2.0 (pinned below 2.1 until OpenTelemetry instruments it), psycopg 3, Alembic.
- Routes take a session as `session: DbSession` (`core_api.db.session`). It commits when the route returns and rolls back when it raises, before the response is sent.
- Tables holding a user's data use the `UserOwned` mixin and are queried only through a `UserScopedRepository`, which cannot be built without a `user_id` and filters every query on it.
- New models are imported in `core_api/db/models/__init__.py`, or Alembic autogenerate does not see them.

## Sync vs async convention (ADR-0005)

- Routes and database access are **synchronous**: use `def`, not `async def`. FastAPI runs `def` routes in a threadpool, so blocking calls do not stall the event loop.
- Never call blocking code (database, `httpx.Client`, file I/O) inside an `async def`.
- PDF/image processing never runs in a request; it belongs to the `ai-service` worker.
