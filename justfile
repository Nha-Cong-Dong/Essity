set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Liệt kê các lệnh
default:
    @just --list

# Sao chép .env.example thành .env nếu chưa có
env:
    @if (-not (Test-Path .env)) { Copy-Item .env.example .env; "Đã tạo .env" } else { ".env đã tồn tại" }

compose := "docker compose --env-file .env -f infra/docker-compose.yml"

# Dựng toàn bộ môi trường local
up:
    {{compose}} up -d --build

# Tắt môi trường local (giữ dữ liệu)
down:
    {{compose}} down

# Xóa sạch dữ liệu local (database, Redis, file) — không khôi phục được
reset:
    {{compose}} down --volumes

# Trạng thái các container
ps:
    {{compose}} ps

# Xem log
logs *args:
    {{compose}} logs -f {{args}}

# Kiểm tra import chéo giữa các dịch vụ (CI cũng chạy)
check-imports:
    uv run --no-project python scripts/check_cross_imports.py

# Kiểm tra giấy phép dependency: chặn GPL/AGPL (ADR-0011, CI cũng chạy)
check-licenses:
    uv run --directory services/core-api --no-sync python ../../scripts/check_licenses.py python
    uv run --directory services/ai-service --no-sync python ../../scripts/check_licenses.py python
    pnpm licenses list --json --filter "web..." | uv run --no-project python scripts/check_licenses.py pnpm -

# Sinh lại packages/api-client từ OpenAPI của core-api (T1.11; CI báo lỗi khi lệch)
gen-api:
    bash scripts/gen_api_client.sh

# Chạy migration của core-api lên database local (cần `just up` trước)
migrate:
    {{compose}} run --rm --no-deps core-api uv run --no-sync alembic upgrade head

# Chạy migration của ai-service lên database `ai` local (cần `just up` trước)
migrate-ai:
    {{compose}} run --rm --no-deps ai-service uv run --no-sync alembic upgrade head
