# Development

## Prerequisites

Docker, Node.js 24+, pnpm, Python 3.13, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just).

## Run locally

```sh
just env                          # create .env from .env.example
just up                           # build and start the stack
just migrate && just migrate-ai   # apply Alembic migrations
just logs                         # tail logs (e.g. just logs core-api)
just down                         # stop, keep data; `just reset` deletes data
```

Endpoints and ports are listed in the root [README](../README.md). `.env.example` uses the fake LLM provider and Mailpit, so no external accounts are needed.

## Tests and checks

| Where | Commands |
|---|---|
| `services/core-api`, `services/ai-service` | `uv sync --locked`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest` (PostgreSQL and Redis required) |
| `apps/web` | `pnpm --filter web lint`, `typecheck`, `test` (Vitest), `build`, `e2e` (Playwright) |
| Repo | `just check-imports`, `just check-licenses`, `python scripts/check_alembic_heads.py`, `python -m unittest discover -s scripts -p "test_*.py"` |

After changing core-api routes, run `just gen-api`; CI fails if `packages/api-client` is stale. Each service keeps a single Alembic head.

## CI

`.github/workflows/ci.yml` runs on push and pull requests, with path-based change detection:

- `python` (matrix core-api, ai-service): licences, ruff, pyright, DB roles, migrations on an empty database, pytest.
- `web`: install, API client freshness, licences, lint, typecheck, unit tests, build, Playwright layout checks.
- `images`: Docker builds, and a check that web refuses to start without `CORE_API_URL`.
- `boundaries`: cross-import check, Alembic heads, repo script tests.
- `secrets`: gitleaks over git history.
- `ci-ok`: single status that fails if any job failed.

## AI-assisted development workflow

This repository is developed with AI coding agents under explicit process controls. This is deliberate: the controls are how quality is maintained at that speed.

- **Parallel lanes.** Independent tasks run in separate git worktrees (`scripts/lane.py`), each with its own test databases and Redis db, so agents do not collide.
- **Task cards and evidence.** Each task has a card (goal, "done when"); agents record evidence per task, and `scripts/flow.py` blocks a merge until it is complete.
- **Review by risk.** High-risk areas (security, data, grading) get a plan review, per-task review and an independent tester that tries to break the code with mutations. Other tasks get one final review.
- **Project-manager gate.** A final checklist with evidence must pass before merge, and CI must be green.
- **Test-driven.** Tests are written first; tests involving locks or timing are repeated before acceptance.
- **Resource limits.** Heavy suites are serialised with `scripts/with_lock.py`; the core-api suite runs in batches (`scripts/core_batches.py`).

Commit messages are in English. Every change goes through a pull request.
