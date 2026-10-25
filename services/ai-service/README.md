# ai-service

LLM tasks, PDF/image processing and evals. Internal only: never exposed to the internet, called by `core-api` alone.

## Commands

```sh
uv sync                  # install dependencies
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type check (strict)
uv run uvicorn ai_service.main:app --reload --port 8001
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
| `AI_LLM_PROVIDER` | yes | `anthropic`, `fake` or `disabled`. `fake` grades without a model and is refused outside `local`/`test`. `disabled` starts without a key; `/v1/grade` answers 503 `grading_disabled` and `/healthz` reports `"grading": "disabled"`. |
| `ANTHROPIC_API_KEY` | with `anthropic` | No `AI_` prefix. Empty counts as missing. |

## Service token

Every request except `GET /healthz` must carry `X-Service-Token: <AI_SERVICE_TOKEN>`; otherwise the response is `401`. This includes `/docs` and `/openapi.json`. The token is compared with `hmac.compare_digest`. It is a second layer behind the private network (ADR-0006), not a replacement for it.

`Authorization` is deliberately not used, so it stays free for user session tokens.

Generate a token:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Sync vs async convention (ADR-0005)

- Routes are **synchronous** by default: use `def`, not `async def`. FastAPI runs `def` routes in a threadpool.
- Never call blocking code (database, `httpx.Client`, file I/O) inside an `async def`. The token middleware is `async` and does no I/O.
- PDF/image processing never runs in a request; it belongs to the worker.
