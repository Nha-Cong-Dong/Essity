# Deploying Essity to one VPS

Goal: a fresh Ubuntu VPS, an IP address and SSH access, and about 20 minutes later the app is live at `https://<ip>.sslip.io`. This is a small-scale setup (demo, review, a few users), not a hardened production platform.

## What you need

| Item | Notes |
|---|---|
| A VPS | Ubuntu 22.04 or 24.04, at least 2 vCPU / 4 GB RAM / 30 GB disk, public IPv4. Ports 80 and 443 must be open in the provider's firewall too (some providers have a separate security-group panel). |
| SSH access | `ssh root@<ip>` (or a sudo user). |
| Gmail App Password | Used to send verification and password-reset emails. See step 3. |
| Anthropic API key | For AI grading. Optional: set `AI_LLM_PROVIDER=disabled` and grading answers 503. |
| Git clone URL | The repository URL; if the repo is private, use an HTTPS URL with a read-only token. |
| Domain (optional) | Without one, the address is `<ip>.sslip.io`. sslip.io is a free DNS service that resolves any name containing an IP to that IP (`203.0.113.10.sslip.io` -> `203.0.113.10`), so HTTPS works with no DNS setup. |

## How it fits together

```
Internet --443--> Caddy (automatic HTTPS) --> web (Next.js) --> core-api --> postgres, redis
                    |                                              \--> ai-service --> Anthropic API
                    +--> s3.<domain> --> storage (RustFS, browser uploads PDFs here)
```

Only Caddy listens on the network (ports 80 and 443). Postgres, Redis, storage and the app services have no published ports. Mailpit, Jaeger and the OpenTelemetry collector (dev tools) are not started.

Files: `infra/docker-compose.prod.yml` (override on top of `infra/docker-compose.yml`), `infra/caddy/Caddyfile`, `.env.prod.example`, `scripts/deploy/bootstrap.sh`, `scripts/deploy/up.sh`.

## Step 1. Connect

```bash
ssh root@<ip>
```

## Step 2. Bootstrap (once)

This installs Docker, opens the firewall (22, 80, 443), adds swap on small machines, clones the repo to `/opt/essity` and creates `/opt/essity/.env.prod` with random secrets and your domain filled in.

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/deploy/bootstrap.sh -o bootstrap.sh
REPO_URL=https://github.com/<owner>/<repo>.git bash bootstrap.sh
```

Optional variables: `BRANCH=<branch>` (default `main`), `DOMAIN=<name>` (default `<detected-ip>.sslip.io`), `SERVER_IP=<ip>` if auto-detection fails.

If the repo is private, copy the script up with `scp scripts/deploy/bootstrap.sh root@<ip>:` and use a token URL for `REPO_URL` (`https://<token>@github.com/<owner>/<repo>.git`).

The script is safe to re-run; it never overwrites an existing `.env.prod`.

## Step 3. Fill in the human values

```bash
nano /opt/essity/.env.prod
```

Replace the placeholders (the script printed them):

- `ACME_EMAIL`: your email; Let's Encrypt sends expiry warnings here.
- `SMTP_USERNAME`, `EMAIL_FROM`: your Gmail address. `SMTP_PASSWORD`: a Gmail App Password. To get one: Google Account -> Security -> turn on 2-Step Verification -> search "App passwords" -> create one named "essity" -> copy the 16 characters (spaces optional).
- `ANTHROPIC_API_KEY`: your key. Or set `AI_LLM_PROVIDER=disabled` (and leave the key as any non-placeholder text such as `none`). `fake` is refused in production.
- `ANTHROPIC_BASE_URL`: leave empty unless you use an Anthropic-compatible proxy.

Do not change the `__GENERATE__`-replaced secrets. Never commit `.env.prod`.

Using your own domain instead of sslip.io: before bootstrap, create two DNS A records pointing at the server IP, `app.example.com` and `s3.app.example.com`, then run bootstrap with `DOMAIN=app.example.com`.

## Step 4. Start

```bash
cd /opt/essity
bash scripts/deploy/up.sh
```

It builds the images (the first build takes 5 to 15 minutes), starts Postgres/Redis/storage, refreshes database roles, runs migrations for core and ai, starts everything and polls `https://<domain>/api/health` for up to 5 minutes. The last line is `UP: https://<domain>`.

Open that link in a browser. The certificate is issued on the first request, so allow a few seconds.

## Update later

```bash
cd /opt/essity && git pull && bash scripts/deploy/up.sh
```

## Everyday commands

Run from `/opt/essity`; set a shortcut first:

```bash
alias dc='docker compose --env-file .env.prod -f infra/docker-compose.yml -f infra/docker-compose.prod.yml'
dc ps                      # state of every service
dc logs -f --tail 100 web core-api   # live logs
dc restart core-api
dc down                    # stop (data kept)
```

Back up before destroying the server: the data lives in Docker volumes `essity_postgres-data`, `essity_storage-data`, `essity_redis-data`. Quick database dump: `dc exec -T postgres pg_dump -U postgres core > core.sql` (and `ai`).

## Turn it off (hourly VPS)

Destroying the VPS deletes everything. To keep the data, dump the databases and download the files first (see above), or keep the machine stopped instead of deleted.

## Troubleshooting

| Symptom | Check |
|---|---|
| `up.sh` says placeholders remain | Edit `.env.prod`; the script lists the lines. |
| Browser says certificate error / site unreachable | Ports 80 and 443 open in the provider panel? `dc logs caddy`. Let's Encrypt limits sslip.io hostnames (shared rate limit); if issuance is refused, retry later or use your own domain. |
| Sign-up works but no verification email | `dc logs core-api core-worker`; wrong App Password or 2-Step Verification off. |
| core-api exits at start with a validation error | `dc logs core-api`: production rules need https URLs, a real SMTP host and STARTTLS, long secrets (>= 32 chars). Fix `.env.prod`. |
| PDF upload fails in the browser | `S3_PUBLIC_ENDPOINT` must be `https://s3.<domain>` and `s3.<domain>` must resolve to the server (automatic with sslip.io). Re-run `up.sh` after changing it, because the web image bakes the origin in at build time. |
| Build killed (out of memory) | Bootstrap adds 2 GB swap; confirm with `free -h`, then re-run `up.sh`. |
| Login locked out for everyone after a few wrong passwords | `WEB_TRUSTED_PROXY_HOPS` must be `1` (Caddy is one proxy). |

## Known limits (accepted for now)

Single server, no automated backups or monitoring, RustFS instead of Cloudflare R2, container images built on the server, secrets stored in a root-only file. Good enough for a review build; revisit before real users.
