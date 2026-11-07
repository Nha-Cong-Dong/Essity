#!/usr/bin/env bash
# One-time server setup for a fresh Ubuntu 22.04/24.04 VPS. Run as root (or with sudo):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/deploy/bootstrap.sh -o bootstrap.sh
#   REPO_URL=https://github.com/<owner>/<repo>.git bash bootstrap.sh
# Safe to re-run. Installs Docker, opens ports 22/80/443, clones the repo, writes .env.prod.
# Variables: REPO_URL (required), BRANCH (default main), APP_DIR (default /opt/essity),
#            SERVER_IP (default: auto-detected public IP), DOMAIN (default: <ip>.sslip.io).
set -euo pipefail

REPO_URL="${REPO_URL:?set REPO_URL to the git clone URL}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/essity}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (sudo bash bootstrap.sh)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Installing packages"
apt-get update -y
apt-get install -y ca-certificates curl git ufw openssl

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker compose version >/dev/null

echo "==> Firewall (22, 80, 443)"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Small VPS: add 2 GB swap so the web build does not run out of memory.
if [ ! -f /swapfile ] && [ "$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)" -lt 6000 ]; then
  echo "==> Adding 2 GB swap"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Fetching code into $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

if [ -f .env.prod ]; then
  echo "==> .env.prod already exists, leaving it alone"
else
  echo "==> Creating .env.prod"
  SERVER_IP="${SERVER_IP:-$(curl -fsS4 https://api.ipify.org || true)}"
  DOMAIN="${DOMAIN:-${SERVER_IP:+$SERVER_IP.sslip.io}}"
  if [ -z "$DOMAIN" ]; then
    echo "Could not detect the public IP: re-run with SERVER_IP=<ip> or DOMAIN=<name>" >&2
    exit 1
  fi
  cp .env.prod.example .env.prod
  chmod 600 .env.prod
  # Replace the example hostname everywhere (DOMAIN, WEB_ORIGIN, S3_* URLs).
  sed -i "s/203\.0\.113\.10\.sslip\.io/$DOMAIN/g" .env.prod
  # Every __GENERATE__ gets its own random value (hex: safe in URLs and YAML).
  while grep -q '__GENERATE__' .env.prod; do
    sed -i "0,/__GENERATE__/s//$(openssl rand -hex 24)/" .env.prod
  done
  echo "    domain: $DOMAIN"
fi

echo
echo "Bootstrap done. Now edit $APP_DIR/.env.prod and replace every FILL-IN / placeholder:"
grep -n -E 'FILL-IN|you@example\.com|your\.address@gmail\.com|xxxx-xxxx' .env.prod || true
echo "Then run: cd $APP_DIR && bash scripts/deploy/up.sh"
