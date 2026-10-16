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
