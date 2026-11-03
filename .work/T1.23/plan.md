# T1.23 — Tên đăng nhập + SĐT liên hệ 🔴 (kế hoạch nhánh `t1.23-username-phone`)

> Mẫu workflow v2 §2. Nguồn: PLAN T1.23, spec us-12 §9 mục 13 (D1–D6), card `.work/T1.23`. Head thật kiểm lại: `0034_roles_grants` (migrations/versions, 34 file); không nhánh nào khác giữ 0035 (BOARD). Số 0035.

## Trạng thái
| Bước | HEAD | Báo cáo cuối | Việc kế |
|---|---|---|---|
| plan | | | security-reviewer plan |
| C1-C4 code | 84d5772 | | review-task |

## Kế hoạch
- **File** (tên trong PLAN `domain/auth/{register,login}.py` KHÔNG tồn tại: logic đăng ký/đăng nhập nằm trong `api/auth.py:87-216`, giữ chỗ đó, không tách file):
  - `migrations/versions/0035_user_username_phone.py` — tạo: thêm cột, backfill bằng Python, NOT NULL, CHECK, UNIQUE.
  - `db/models/user.py` — sửa: `username` (String(20), unique), `phone` (String(16) null), CHECK `username_format` (`username = lower(username) AND username ~ '^[a-z][a-z0-9_.]{2,19}$' AND position('..' in username)=0`).
  - `domain/auth/username.py` — tạo, hàm thuần: `normalize_username`, `validate_username` (+ `RESERVED`), `username_from_email(email, taken)` (dùng cho backfill và T5.10).
  - `domain/auth/phone.py` — tạo, hàm thuần: `normalize_phone` → `+84…` hoặc lỗi.
  - `repositories/user.py:21-39` — sửa: `create(email, password_hash, timezone, *, username=None, phone=None)`; `username=None` tự sinh + retry (giữ ~40 chỗ gọi test như `tests/accounts.py:14`, `tests/erase_world.py:41` không đổi); `UsernameTakenError` tách khỏi `EmailTakenError` theo tên constraint; thêm `get_by_username`.
  - `api/auth.py` — sửa: `RegisterBody` (+`username`, `phone`), `LoginBody` (`identifier`, `email` bí danh), khóa rate limit, `security_event`.
  - `security/audit.py:42` — sửa: tham số `identifier` → ghi `identifier_hash` (HMAC như `hash_ip`), không ghi thô.
  - `logging.py:82` — sửa: thêm `phone` vào khóa bị che/loại (kiểm cách formatter).
  - `contracts/openapi` + `packages/api-client` — tái sinh bằng `scripts/gen_api_client.py`.
  - Test mới ở `tests/auth/` và `tests/db/`.
- **Dùng lại:** `dummy_verify`, `hash_password` (`domain/auth/passwords.py`); `normalize_email` (`domain/email.py:4`); `RateLimit/hit/refund` (`api/auth.py:61-62,180-202`); `hash_ip` (`security/audit.py:31`); savepoint IntegrityError (`repositories/user.py:31-36`); `signed_in` (`tests/accounts.py:13`).
- **Migration:** 0035 (revision `0035`, down `0034`). Downgrade bỏ cột + constraint (additive).
- **Thứ tự commit** (push sau mỗi cụm): C1 migration + model + test migration/ràng buộc; C2 domain username/phone + repository (test thuần); C3 register; C4 login + security_event; C5 contract + api-client. Bảng `spec/README.md` do điều phối cập nhật.

## Test viết trước
| AC / quy tắc | Tên test | Đỏ khi |
|---|---|---|
| D6 backfill | `test_0035_backfills_username_from_email_local_part` (ca: `A.B@x`→`a.b`; `9lives@`; `ab@`; `a..b@`; `x+tag@`; 40 ký tự; `admin@`; `bob@a`,`bob@b`,`bob_2@c` + 1 xóa mềm) | thiếu hậu tố, trùng, ký tự sai, bắt đầu số, <3/>20, tên giữ chỗ, hoặc mất dữ liệu/mật khẩu cũ |
| D6 | `test_0035_downgrade_then_upgrade_keeps_users` | downgrade xóa user |
| D2/AC1 | `test_username_rejects_bad_shapes` (2/21 ký tự, `1abc`, `12345`, `a@b`, `a..b`, `Ab c`, giữ chỗ); `test_db_check_refuses_uppercase_username` | thiếu luật; DB nhận chữ hoa |
| D2/AC1 | `test_register_username_case_insensitive_duplicate` → 409 `username_taken` | `Bob`/`bob` cùng lọt |
| AC5 | `test_register_taken_email_still_check_email`; `test_register_taken_email_new_username_same_response_as_new_email` | lộ email đã có |
| AC5 | `test_username_taken_independent_of_email_state` | 409 phụ thuộc email tồn tại |
| D4/AC1 | `test_phone_normalizes_to_e164` (`0912345678`, `84912345678`, `+84912345678`); `test_phone_rejects_invalid`; `test_two_accounts_share_phone`; `test_register_optional_phone` | chuẩn hóa sai; phone bị unique |
| AC1 | `test_register_existing_email_does_not_overwrite_phone_or_username` | ghi đè user cũ |
| D3/AC5 | `test_login_by_username`, `test_login_by_email_via_identifier`, `test_login_email_alias_still_works`, `test_login_phone_is_not_identifier` | 200 khi nhập SĐT; alias hỏng |
| D3 | `test_login_identifier_is_trimmed_and_lowercased` | `  Bob ` không vào |
| AC5 | `test_login_all_failures_same_401_body` (user sai, email sai, mật khẩu sai); `test_login_unknown_username_runs_dummy_verify` (mock đếm) | thông báo/đường đi khác |
| AC6 | `test_login_pair_limit_5_per_identifier_ip`, `test_login_identifier_limit_20`, `test_login_correct_password_refunds` | không 429; không hoàn lượt |
| AC6/ADR-0013 | `test_security_event_never_logs_raw_identifier_or_phone` (caplog: login sai, đăng ký có SĐT) | log thô |
| ADR-0024 | `test_core_app_can_write_username_phone_and_eraser_deletes_row` (kiểu `tests/db/test_roles.py`) | grants thiếu |
| Hợp đồng | `test_openapi_login_identifier_and_register_fields`; `scripts/test_gen_api_client.py` | api-client cũ |

## Rủi ro và ca biên
- Backfill trên dữ liệu thật: chạy thử trên bản sao DB dev có user thật; `deleted_at` cũng điền (UNIQUE tính cả hàng xóa mềm); email nhiều `@`/phần trước rỗng.
- Đua đăng ký cùng username: UNIQUE + savepoint, phân biệt constraint; test 2 request đồng thời.
- Hai bí danh (username, email) của một tài khoản có khóa đếm riêng: tối đa 2× lượt/tài khoản (10 thay vì 5 mỗi cặp IP). Chấp nhận (D3 "định danh đã chuẩn hóa"), vẫn có trần 20/định danh. Báo security-reviewer.
- Người dùng gõ mật khẩu vào ô định danh: không log thô (hash).
- Thời gian: tra theo unique index như email; nhánh `dummy_verify` giữ; không tra SĐT.
- Mật khẩu `SAME_AS_EMAIL` giữ; không thêm luật theo username.
- Tái sinh api-client đổi kiểu `LoginBody`; web (T1.24, không chạm) vẫn gửi `email`: chạy `pnpm typecheck` chỉ để xác nhận, không sửa web.

## Quyết định
| Quyết định | Lý do | Chốt bởi | Ngày |
|---|---|---|---|
| Backfill bằng vòng lặp Python trong migration (không `row_number` SQL): phần trước `@`, lower, bỏ ký tự ngoài `a-z0-9_.`, bỏ ký tự đầu không phải chữ, gộp `..`→`.`, rỗng → `user`, <3 đệm `_` tới 3, cắt 20; trùng hoặc giữ chỗ → `<base cắt>_2`, `_3`… theo `created_at, id`, kiểm tập đã dùng | `row_number` không chống được `bob_2` có sẵn; bảng nhỏ, kết quả xác định | Coder | 03/11 |
| Đăng ký chuẩn hóa `strip+lower` rồi mới kiểm D2 (`Bob`→`bob`) | D2 "lưu chữ thường"; AC1 trùng không phân biệt hoa thường | Coder | 03/11 |
| 422 `detail` mã: `username_invalid`, `username_reserved`, `phone_invalid`; 409 `username_taken` kiểm sau `REGISTER_PER_IP`, trước cooldown email và băm, không phụ thuộc email | Khớp kiểu lỗi mật khẩu; AC5 | Coder | 03/11 |
| Đăng nhập: `strip+lower`, có `@` → email, không → username; không regex lúc đăng nhập (sai dạng = 401) | D3 + `LoginEmail` cũ (`api/text.py:70`) | Coder | 03/11 |
| `LoginBody`: `identifier` và `email` (bí danh) cùng tùy chọn, cần ≥ một (thiếu → 422); có cả hai thì dùng `identifier`; `extra="forbid"` giữ; gỡ bí danh sau T1.24 | `apps/web/app/api/auth/login/route.ts:16` còn gửi `email` | Coder | 03/11 |
| Khóa giới hạn: `login_identifier_ip` = `identifier|ip`, `login_identifier` = `identifier` (đổi tiền tố Redis; đếm đang chạy mất, chấp nhận) | D3, ADR-0020 | Coder | 03/11 |
| `security_event(identifier=...)` ghi `identifier_hash` (HMAC khóa log, 16 hex); email vẫn `email=` (bị che); SĐT không bao giờ vào log | `mask_email` chỉ hợp email (`logging.py:124`); username có thể là mật khẩu gõ nhầm | Coder | 03/11 |
| `create(username=None)` tự sinh qua `username_from_email` + hậu tố ngẫu nhiên, thử lại khi trùng. Seed/demo: `cli.py:51`, `cli_seed.py:143` chỉ tra `get_by_email`, `demo.py` nhận User có sẵn, không đường tạo user nào khác cần sửa | Giữ test cũ; T5.10 dùng lại | Coder | 03/11 |
| Không chạm RLS/grants/eraser: `GRANT … ON ALL TABLES` + default privileges của 0034 phủ cột mới (cấp theo bảng); xóa user là xóa hàng nên xóa luôn username/phone; chưa có RLS (T6.1); chỉ thêm test | Cột mới thuộc bảng `user` sẵn có | Coder | 03/11 |
| Không thêm `username`/`phone` vào `/v1/me` | Ngoài "Xong khi"; T1.24 cần thì thêm | Coder | 03/11 |

## Câu hỏi mở
Không có.

| P1 review: giữ chỗ username khi email đã có tài khoản: Redis `username_hold:<sha>` TTL 7 ngày (= UNVERIFIED_LIFETIME), đặt ở nhánh EmailTakenError; 409 xét hàng user lẫn hold; Redis lỗi thì 503 (fail closed) | đóng kênh bậc hai dò email (AC5); dễ đảo ngược, không schema | Coder | 03/11 |
| P2: không thêm bộ đếm theo user_id sau tra cứu (429 chỉ có ở tài khoản thật sẽ lộ email) | review plan | Coder+security-reviewer | 03/11 |
| Web (T1.24) chưa gửi `username`: `apps/web/app/api/auth/register/route.ts:17` hết typecheck, đăng ký web 422 tới khi T1.24 merge | LoginBody/RegisterBody theo card; do_not_touch apps/web | Coder | 03/11 |
| R1: hold 7 ngày vs purge mỗi giờ lệch ≤ 1 giờ | kênh chậm, chấp nhận | Coder+security-reviewer | 03/11 |
| R4: T5.10 `create(username=None)` phải xét USERNAME_HOLD khi tự sinh tên (ghi cho card T5.10) | ngoài T1.23 | Coder | 03/11 |
| SĐT hoãn tới khi có nhà cung cấp SMS: bỏ cột `phone`, trường API, chuẩn hóa +84, test D4 (người dùng 03/11) | ngân sách, không có SMS | người dùng | 03/11 |
| D7 Họ và tên: `user.display_name` text NULL + CHECK 1-60; API trim, rỗng -> NULL, >60 -> 422 `display_name_too_long`; `/v1/me` trả `username` + `display_name` | người dùng duyệt mẫu form 03/11 | Claude sau design-director + design-critic | 03/11 |
| D8 `GET /v1/auth/username-availability?u=`: 30 lần/phút/IP, tên bị hold tính "taken", không cần phiên | T1.24 cần kiểm khi rời ô | Coder | 03/11 |
