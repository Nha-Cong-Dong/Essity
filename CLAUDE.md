# CLAUDE.md

Essity: AI-graded spaced-repetition app. Full documentation: [documentation/](documentation/README.md).

## Layout

- `apps/web`: Next.js UI and BFF
- `services/core-api`: FastAPI, source of truth (auth, scheduling, grading orchestration)
- `services/ai-service`: FastAPI, LLM calls and document processing
- `packages/api-client`: generated TypeScript client (`just gen-api`)
- `contracts/`: JSON Schemas for events and files
- `infra/`: Docker Compose, Postgres roles, OTel
- `scripts/`: repo checks and workflow tooling

## Commands

- `just env`, `just up`, `just migrate`, `just migrate-ai`, `just down`
- Python services: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest`
- Web: `pnpm --filter web lint`, `typecheck`, `test`, `build`
- Repo: `just check-imports`, `just check-licenses`

## Rules

- core-api and ai-service must not import each other.
- Regenerate `packages/api-client` after changing core-api routes.
- One Alembic head per service; do not edit merged migrations.
- Every LLM call goes through ai-service and its quota; a model needs a price in `llm/pricing.py`.
- Never commit secrets or `.env`.
- Test first; run lint, format check and type check before committing.
- Commit messages in English, no co-author trailers.

See [documentation/DEVELOPMENT.md](documentation/DEVELOPMENT.md) and [documentation/ARCHITECTURE.md](documentation/ARCHITECTURE.md).
