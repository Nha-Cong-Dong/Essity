# Essity

AI-graded spaced repetition. Answer a daily set of questions drawn from your own notes and textbooks; the schedule adapts to what you actually remember.

> **Status:** pre-alpha. Under active development; interfaces and schemas will change.

## Features

- **Daily session.** A prioritized queue of questions, ranked by forgetting risk and exam proximity.
- **Free-text answers.** No self-rating. Answers are graded against source passages from your own material.
- **Per-concept scheduling.** [FSRS](https://github.com/open-spaced-repetition/py-fsrs) tracks memory state for each knowledge unit.
- **Source-anchored.** Every question and grade links back to the exact page it came from.
- **Reproducible.** Raw data is immutable; every AI output is versioned by prompt and model and can be re-run.

## Architecture

| Service | Stack | Responsibility |
|---|---|---|
| `apps/web` | Next.js, TypeScript, Tailwind, shadcn/ui | UI and thin BFF |
| `services/core-api` | FastAPI, SQLAlchemy, py-fsrs | Auth, review logic, scheduling; source of truth |
| `services/ai-service` | FastAPI, worker | LLM calls, PDF/image processing, evals |

**Infrastructure:** PostgreSQL (one database per service), Redis Streams, S3-compatible object storage, OpenTelemetry.

**Communication:** synchronous HTTP for user-facing calls (grading); Redis Streams with a transactional outbox for long-running jobs.

## Project layout

```
apps/web/              Next.js frontend
services/core-api/     Core API
services/ai-service/   AI service and worker
packages/api-client/   TypeScript client generated from OpenAPI
contracts/events/      JSON Schemas for inter-service events
infra/                 Docker Compose, backup scripts
scripts/               Repo checks run by CI
```

## Getting started

**Prerequisites:** Docker, Node.js 24+, pnpm, Python 3.13, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just)

```sh
just env    # create .env from .env.example
just up     # build and start the local stack
just ps     # container status and health
just logs   # tail service logs (optionally: just logs core-api)
just down   # stop, keep data
just reset  # stop and delete all local data
```

Local endpoints (bound to `127.0.0.1` only):

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| core-api | http://localhost:8000 |
| ai-service | http://localhost:8001 (requires `X-Service-Token`) |
| Mailpit (captured email) | http://localhost:8025 |
| Jaeger (traces) | http://localhost:16686 |
| Object storage console (RustFS) | http://localhost:9001/rustfs/console/ |
| PostgreSQL | `localhost:5432`, databases `core` and `ai`, one user each |
| Redis | `localhost:6379` |

## License

Not yet specified. All rights reserved until a `LICENSE` file is added.
