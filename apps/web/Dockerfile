# Build context: repo root (pnpm workspace + lockfile live there).
#   docker build -f apps/web/Dockerfile .
FROM node:24-slim AS deps
RUN npm install -g pnpm@12.11.2
WORKDIR /repo
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
# `web...`: web and the workspace packages it depends on, with their own dependencies.
RUN pnpm install --frozen-lockfile --filter web...

FROM deps AS build
COPY packages packages
COPY apps/web apps/web
# T4.6: next.config.ts bakes the CSP into the build, so the storage's origin is a build argument.
ARG UPLOAD_ORIGIN=
ENV UPLOAD_ORIGIN=$UPLOAD_ORIGIN
RUN pnpm --filter web build

FROM node:24-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
