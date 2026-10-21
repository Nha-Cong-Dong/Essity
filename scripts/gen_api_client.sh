#!/usr/bin/env bash
# T1.11: regenerate packages/api-client from core-api's OpenAPI document.
# CI runs the same steps and fails when the committed files differ.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
uv run --directory "$root/services/core-api" --no-sync \
  python -m core_api.openapi_export "$root/packages/api-client/openapi.json"
pnpm --dir "$root/packages/api-client" generate
