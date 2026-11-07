# Deployment

TODO: to be completed by the deployment work. Deployment instructions will live in `infra/DEPLOY.md`; see that file when it lands.

Until then: `infra/docker-compose.yml` defines the local stack, and each service validates its environment at start (`CORE_ENVIRONMENT`, `AI_ENVIRONMENT`: `local`, `test`, `staging`, `production`). Outside `local` and `test`, local-only values (Mailpit, `localhost`, no STARTTLS) are refused.
