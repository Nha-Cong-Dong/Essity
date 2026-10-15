set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Liệt kê các lệnh
default:
    @just --list

# Sao chép .env.example thành .env nếu chưa có
env:
    @if (-not (Test-Path .env)) { Copy-Item .env.example .env; "Đã tạo .env" } else { ".env đã tồn tại" }

# Dựng toàn bộ môi trường local (có từ T0.5)
up:
    docker compose -f infra/docker-compose.yml up -d --build

# Tắt môi trường local
down:
    docker compose -f infra/docker-compose.yml down

# Xem log
logs *args:
    docker compose -f infra/docker-compose.yml logs -f {{args}}
