# ai-service

LLM tasks, PDF/image processing and evals. Internal only: never exposed to the internet, called by `core-api` alone.

## Commands

```sh
uv sync                  # install dependencies
uv run pytest            # tests (needs AI_TEST_DATABASE_URL, below)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check (strict)
uv run uvicorn ai_service.main:app --reload --port 8001
```

Database tests run on a real PostgreSQL, in a database of their own that the tests create if
missing. `AI_TEST_DATABASE_URL` has no default; without it those tests fail and say so. A
throwaway server that leaves the local Compose data alone:

```sh
docker run -d --name pg-ai-test -e POSTGRES_PASSWORD=x -p 127.0.0.1:55432:5432 postgres:18-alpine
export AI_TEST_DATABASE_URL=postgresql+psycopg://postgres:x@127.0.0.1:55432/ai_test
```

## Layout

```
src/ai_service/
  api/            internal HTTP routes
  tasks/          one module per AI task (grade, extract, ...)
  llm/            provider adapters, pricing, llm_call logging
  pdf/            PDF reading behind an interface (ADR-0011)
  security.py     service token check
```

## Configuration

Environment variables prefixed with `AI_` (see `config.py`).

| Variable | Required | Notes |
|---|---|---|
| `AI_SERVICE_TOKEN` | yes | Shared secret, at least 32 characters. The service will not start without it. |
| `AI_DATABASE_URL` | yes | `postgresql+psycopg://…/ai`. Holds `pipeline_run` and `llm_call` (the audit log of AI work). Migrations: `just migrate-ai`, or `uv run alembic upgrade head` here. |
| `AI_LLM_PROVIDER` | yes | `anthropic`, `fake` or `disabled`. `fake` grades without a model and is refused outside `local`/`test`. `disabled` starts without a key; `/v1/grade` answers 503 `grading_disabled` and `/healthz` reports `"grading": "disabled"`. |
| `ANTHROPIC_API_KEY` | with `anthropic` | No `AI_` prefix. Empty counts as missing. |

## Service token

Every request except `GET /healthz` must carry `X-Service-Token: <AI_SERVICE_TOKEN>`; otherwise the response is `401`. This includes `/docs` and `/openapi.json`. The token is compared with `hmac.compare_digest`. It is a second layer behind the private network (ADR-0006), not a replacement for it.

`Authorization` is deliberately not used, so it stays free for user session tokens.

Generate a token:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Grading: `POST /v1/grade`

Grades one answer against the learner's sources (T2.12). The contract and its limits are in `tasks/grade_models.py`, the error codes in `api/grade.py`. In short:

- Each request writes a `pipeline_run` before any model call. Each call writes an `llm_call` row in its own transaction, including calls that fail. If either write fails, the response is 503 `audit_unavailable` and no grade is returned.
- Every untrusted field is escaped and wrapped in a nonce-tagged data block (`wrap_untrusted`). The system prompt (`prompts/grade/v1.md`) holds instructions only.
- The output is checked by code (R03). On a violation the model is asked once more; a second violation is 502 `grade_invalid`. `overall` is derived by the code, never taken from the model.
- An empty answer is graded `incorrect` without a model call.
- The whole request has 9 s.

## Sync vs async convention (ADR-0005)

- Routes are **synchronous** by default: use `def`, not `async def`. FastAPI runs `def` routes in a threadpool.
- Never call blocking code (database, `httpx.Client`, file I/O) inside an `async def`. The token middleware is `async` and does no I/O.
- PDF/image processing never runs in a request; it belongs to the worker.
