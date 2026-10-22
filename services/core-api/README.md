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
uv run python -m core_api.jobs.worker                         # background job worker
uv run alembic upgrade head                                   # apply migrations
uv run alembic revision --autogenerate --rev-id 0003 -m "..."  # new migration
uv run alembic check                                          # models match migrations
```

## Layout

```
src/core_api/
  api/            routes: parse input, call domain, return output
  domain/         business rules; no HTTP, no SQL
  repositories/   database access; every function takes user_id
  clients/        external services (ai-service, email, storage)
  jobs/           background jobs (Procrastinate); the only package importing it
```

## Configuration

Environment variables prefixed with `CORE_` (see `config.py`). Required, or core-api does not start:

- `CORE_DATABASE_URL`: `postgresql+psycopg://user:password@host:5432/core`. Migrations need only this one.
- `CORE_AI_SERVICE_TOKEN`: at least 32 characters, same value as `AI_SERVICE_TOKEN` in ai-service.
- `CORE_REDIS_URL`: `redis://host:6379/0` (rate limits).

Optional: `CORE_WEB_TOKEN` (at least 32 characters), the token web sends in `X-Service-Token`. Only requests carrying it may pass the user's IP in `X-Client-IP`; without it set, that header is ignored and `X-Forwarded-For` is never trusted.

Tests use `CORE_TEST_DATABASE_URL` (default: the Compose Postgres, database `core_test`) and `CORE_TEST_REDIS_URL` (default: the Compose Redis, database 15). Each test runs in a transaction that is rolled back, and tests run in random order (`pytest-randomly`).

**Two runs at once need their own database and Redis database** (R32): some tests migrate the schema down and up, or empty the job tables, so two runs on one database fail each other (measured: 12 and 13 failures side by side on one database, none on two). Create one per run, e.g. `createdb core_test_2`, and set `CORE_TEST_DATABASE_URL=…/core_test_2` and `CORE_TEST_REDIS_URL=…/14`.

## Database

- SQLAlchemy 2.0 (pinned below 2.1 until OpenTelemetry instruments it), psycopg 3, Alembic.
- Routes take a session as `session: DbSession` (`core_api.db.session`). It commits when the route returns and rolls back when it raises, before the response is sent.
- Tables holding a user's data use the `UserOwned` mixin and are queried only through a `UserScopedRepository`, which cannot be built without a `user_id` and filters every query on it.
- New models are imported in `core_api/db/models/__init__.py`, or Alembic autogenerate does not see them.

## Rate limits

`core_api.security.rate_limit`: a `RateLimit(name, limit, window)` rule and a `RateLimiter` (dependency `get_rate_limiter`). `limiter.enforce(rule, key)` counts an attempt and answers 429 with `Retry-After` when over the limit; `check` looks without counting. Keys (emails, IPs) are hashed before reaching Redis. If Redis is unreachable the limiter answers 503 instead of letting requests through. Per-IP keys come from `security.client_ip.client_ip`.

## Background jobs (ADR-0014)

Jobs run in the `core-worker` process (`python -m core_api.jobs.worker`), on Procrastinate with PostgreSQL as the queue.

- `enqueue_job(session, kind, payload)` (`core_api.jobs.queue`) writes the job in the session's transaction: no job if the route rolls back, visible to workers once it commits. Unknown kinds and non-JSON payloads are refused at once.
- Handlers are synchronous functions declared in `core_api/jobs/registry.py` with `@job_handler("<kind>")`. They receive the payload as a dict and may run more than once for the same job, so they must be idempotent.
- A failing handler is retried after 10 s, 30 s, 90 s and 270 s; after the fifth failure the job stays in `procrastinate_jobs` with status `failed`.
- On SIGTERM the worker takes no new job and waits up to 20 s for the running one.
- Payloads may hold personal data: they are never logged, and Procrastinate's own log lines keep only their event name.
- Procrastinate's schema comes from migration `0002` (SQL frozen in `migrations/sql/`). Upgrading Procrastinate means a new migration with its migration SQL, never `procrastinate schema --apply`.

## Sync vs async convention (ADR-0005)

- Routes and database access are **synchronous**: use `def`, not `async def`. FastAPI runs `def` routes in a threadpool, so blocking calls do not stall the event loop.
- Never call blocking code (database, `httpx.Client`, file I/O) inside an `async def`.
- PDF/image processing never runs in a request; it belongs to the `ai-service` worker.
