# Development

## Prerequisites

Docker, Node.js 24+, pnpm, Python 3.13, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just). The `justfile` uses PowerShell on Windows.

## Run locally

```sh
just env                          # create .env from .env.example
just up                           # build and start the stack
just migrate && just migrate-ai   # apply Alembic migrations
just logs core-api                # tail logs of one service
just down                         # stop, keep data; `just reset` deletes data
```

`.env.example` uses the fake LLM provider and Mailpit, so no external accounts are needed. Ports and URLs are listed in the root [README](../README.md). Open the app at `http://localhost:3000`; `127.0.0.1` is rejected by the origin check.

To run a service outside Compose (`pnpm dev`, `uvicorn --reload`), set its environment yourself, for example `CORE_ENVIRONMENT=local`. The OTel collector listens on `127.0.0.1:4318` for such processes.

Helper commands in `services/core-api/src/core_api/`: `cli_seed.py`, `cli_demo_account.py`, `cli_review_account.py` (seed data and demo accounts), `cli_export_eval.py` (consented eval export).

## Tests and checks

| Where | Commands |
|---|---|
| `services/core-api`, `services/ai-service` | `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest` (PostgreSQL and Redis required) |
| `apps/web` | `pnpm --filter web lint`, `typecheck`, `test` (Vitest), `build` |
| `apps/web` e2e | `pnpm --filter web e2e` (Playwright) |
| Repo | `just check-imports`, `just check-licenses`, `python scripts/check_alembic_heads.py`, `python -m unittest discover -s scripts -p "test_*.py"` |

### Playwright

By default the config starts the standalone build (`node .next/standalone/apps/web/server.js`, prepared by `apps/web/scripts/prepare-standalone.mjs`) and runs layout and UI specs against the design previews. With `E2E_STACK_URL` set, no server is started and the specs run against that URL; this is how `email-verify.spec.ts` checks verification email through Mailpit.

```sh
just up && just migrate && just migrate-ai
E2E_STACK_URL=http://localhost:3000 pnpm --filter web e2e
```

### Smoke test

`scripts/smoke_stack.py` exercises a running stack end to end.

## API client

After changing core-api routes, regenerate the client and commit the result:

```sh
just gen-api
```

CI fails if `packages/api-client` is stale.

## Migrations

Each service has one Alembic head (`services/core-api/migrations/`, `services/ai-service/migrations/`), checked by `scripts/check_alembic_heads.py`. Do not edit merged migrations. Run them with `just migrate` and `just migrate-ai`. On an old Postgres volume, run `just db-roles` before `just migrate` to create the restricted `core_app` and eraser roles.

## CI

`.github/workflows/ci.yml` runs on push and pull requests, with path-based change detection:

| Job | Checks |
|---|---|
| `python` (core-api, ai-service) | licences, ruff, format, pyright, DB roles, migrations on an empty database, pytest |
| `web` | install, API client freshness, licences, lint, typecheck, unit tests, build, Playwright |
| `images` | Docker builds; web refuses to start without `CORE_API_URL` |
| `boundaries` | cross-import check, Alembic heads, repo script tests |
| `secrets` | gitleaks over git history |
| `ci-ok` | single status that fails if any job failed |

## Conventions

- Tests first; run lint, format check and type check before committing.
- core-api and ai-service must not import each other.
- Every LLM call goes through ai-service and its quota; a model needs a price in `llm/pricing.py`.
- Never commit secrets or `.env`.
- Commit messages in English, no co-author trailers; every change goes through a pull request.

## AI-assisted development workflow

This repository is developed with AI coding agents under explicit process controls.

- **Parallel lanes.** Independent tasks run in separate git worktrees (`scripts/lane.py`), each with its own test databases and Redis db.
- **Task cards and evidence.** Each task has a card (goal, "done when"); `scripts/flow.py` blocks a merge until the evidence is complete.
- **Review by risk.** High-risk areas (security, data, grading) get a plan review, per-task review and an independent tester that mutates the code. Other tasks get one final review.
- **Gate.** A final checklist with evidence must pass and CI must be green before merge.
- **Resource limits.** Heavy suites are serialised with `scripts/with_lock.py`; the core-api suite runs in batches (`scripts/core_batches.py`).
