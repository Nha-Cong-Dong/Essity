# web

Next.js UI and thin BFF. The browser only talks to `web`; `web` calls `core-api` from the server (ADR-0004). No business logic here.

## Commands

Run from `apps/web` (dependencies are installed from the repo root with `pnpm install`):

```sh
pnpm dev         # http://localhost:3000
pnpm lint        # ESLint
pnpm typecheck   # route types + tsc --noEmit
pnpm build       # production build (standalone output)
```

## Layout

```
app/              routes (App Router)
app/api/          route handlers (BFF)
lib/core.ts       server-only client for core-api
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `CORE_API_URL` | `http://127.0.0.1:8000` | Read on the server only. Never prefix with `NEXT_PUBLIC_`. |

## Conventions

- Next.js is pinned to an exact version (`16.4.2`). Its own docs ship in `node_modules/next/dist/docs/`; check them before relying on remembered APIs (see `AGENTS.md`).
- Anything that calls `core-api` imports `server-only`, so it fails the build if pulled into a client component.
- `GET /api/health` returns `200` when `core-api` answers `/healthz`, otherwise `503`.

## Docker

The build context is the repo root:

```sh
docker build -f apps/web/Dockerfile .
```
