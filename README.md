# Essity

> Ôn tập thông minh cho người hay mất năng lượng trước khi bắt đầu học.
> *A spaced-repetition study app that decides what to review so you never have to.*

## Vấn đề

Ngồi vào bàn học mà không biết hôm nay nên ôn gì sẽ ngốn hết năng lượng trước khi học thật. Essity bỏ bước đó: mỗi ngày app đưa ra **một phiên câu hỏi cụ thể**, bạn trả lời tự do, AI chấm dựa trên chính ghi chú và giáo trình của bạn, và lịch ôn tự điều chỉnh theo mức nhớ thực tế. Không nhập liệu có cấu trúc, không tự chấm "mình thuộc tới đâu".

## Cách hoạt động

1. Ghi lại buổi học bằng một câu tự nhiên, kèm ảnh vở nếu có.
2. AI tách nội dung thành các **mảnh kiến thức** (mỗi mảnh một ý, có neo về trang gốc) và sinh câu hỏi.
3. Mỗi ngày, **Phiên hôm nay** chọn các câu có nguy cơ quên cao nhất, ưu tiên môn sắp thi.
4. Bạn trả lời, AI chấm theo nguồn của bạn, lịch [FSRS](https://github.com/open-spaced-repetition/py-fsrs) cập nhật theo từng mảnh.

## Kiến trúc

Ba dịch vụ trong một monorepo:

| Dịch vụ | Công nghệ | Vai trò |
|---|---|---|
| `apps/web` | Next.js, TypeScript, Tailwind, shadcn/ui | Giao diện và BFF mỏng |
| `services/core-api` | Python, FastAPI, SQLAlchemy, py-fsrs | Tài khoản, nghiệp vụ ôn tập, lịch FSRS; nguồn sự thật của dữ liệu |
| `services/ai-service` | Python, FastAPI, worker | LLM, xử lý PDF/ảnh, eval |

Hạ tầng: PostgreSQL (mỗi dịch vụ một database), Redis Streams, S3-compatible storage (MinIO/R2), OpenTelemetry.

```
apps/web/              Next.js
services/core-api/     FastAPI
services/ai-service/   FastAPI + worker
packages/api-client/   client TypeScript sinh từ OpenAPI
contracts/events/      JSON Schema cho sự kiện giữa dịch vụ
infra/                 Docker Compose, sao lưu
```

## Bắt đầu

Yêu cầu: Docker, Node.js 24+ với pnpm, Python 3.13 với [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just).

```sh
just env   # tạo .env từ .env.example
just up    # dựng môi trường local (có từ giai đoạn 0)
```

## Trạng thái

Đang ở **giai đoạn 0: khung xương** — dựng một đường chạy mỏng xuyên ba dịch vụ trước khi viết tính năng. Dự án đang được xây dựng công khai, thay đổi thường xuyên.

## Giấy phép

Chưa chọn giấy phép. Mặc định bảo lưu mọi quyền cho đến khi có `LICENSE`.
