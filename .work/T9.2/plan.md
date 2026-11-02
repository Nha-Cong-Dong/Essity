# T9.2 — core-api: áp lệnh và hoàn tác 🔴 (kế hoạch nhánh `t9.2-plan`)

> Chỉ kế hoạch. Ước 8–9 h, tách 4 sub-task ≤ 3 h (W10). Nguồn: PLAN.md:825-838, ADR-0030, ADR-0008:25-40, ADR-0029:22-30, spec US-18 AC4/5/6/9.

## Trạng thái
| Bước | HEAD | Báo cáo cuối | Việc kế |
|---|---|---|---|
| Kế hoạch | main 9fff3d2 | chưa review | tech-expert chốt F2 + command_id; security-reviewer 1 vòng; rồi giao T9.2b (cần L1) |

## Hiện trạng (đã đọc)
- Lõi thuần T9.2a: `domain/commands/apply.py:41` (`apply_command`, Snapshot→Snapshot, `LoggedCommand`), `inverse.py:36-44` (diff, `Revert` có `expected_rev`), `undo.py:27-62` (`undo_latest`, mã `nothing_to_undo|other_session|changed_after`), `registry.py:328,338` (`run_op`, `op_from_json`), `state.py` (Snapshot: Card/Section/Question/StudyFilter, có `rev`).
- Bảng `command_log` đã có ở 0025 (`db/models/command.py:27-60`): `ops_json`, `inverse_json`, `status`, `affected_count`, `screen_session_id`, `seq`. Trigger `command_log_guard` (0025:44-62) chỉ cho đổi `applied→undone` một lần, cấm sửa mọi cột khác.
- **Thiếu so với lõi (cần migration, L1):** (a) không có cột `command_id` → idempotent theo `command_id` (T9.3a) không có chỗ giữ; (b) `LoggedCommand.undo_revs` (`apply.py:23`) không có cột và trigger cấm sửa `inverse_json`; (c) `Snapshot` không có bảng cho `StudyFilter` (spec §9 mục 7: "chốt ở T7.10 và T9.2") và `Question.in_practice` không có cột (`grep in_practice db/models` rỗng).
- Không có thư mục `services/commands`; ánh xạ vào application service hiện có: `OutlineService` (`services/outline.py:93`), `services/practice.py:79,86` (`remove`/`readd`), `repositories/unit.py` (`lock`, `lock_drafts`, `add_revision`, `insert_draft`), `repositories/question.py`.

## Kế hoạch: sub-task
| # | Sub-task | Ước | Touches | Cần L1 |
|---|---|---|---|---|
| T9.2b | Migration nhỏ + repository `command_log` | 2 h | `migrations/versions/0032_command_log_idempotency.py`, `db/models/command.py`, `repositories/command_log.py`, `tests/schema_v2/` | **Có** (một Alembic head; số đề xuất 0032, kiểm lại BOARD lúc cấp) |
| T9.2c | Áp lệnh trong một transaction: nạp/ghi Snapshot, idempotent | 3 h | `services/commands.py` (mới), `repositories/command_log.py`, `repositories/{unit,doc_section,question}.py` (chỉ thêm hàm nạp/ghi), tests | Không |
| T9.2d | Hoàn tác mới nhất trước + kiểm `rev` | 2.5 h | `services/commands.py`, `repositories/command_log.py`, tests | Không |
| T9.2e | API + cách ly/chưa xác minh/đồng thời + lọc gợi ý móc | 2.5 h | `api/commands.py`, `api/__init__.py` đăng ký router, `services/suggestions.py` (móc lọc), `tests/api/`, hợp đồng OpenAPI | **Có**: sinh lại api-client (`packages/api-client`) sau merge |

Thứ tự: T9.2b → T9.2c → T9.2d → T9.2e (tuần tự; T9.2d cần bản ghi từ T9.2c). T9.2b là cổng L1; T9.2c–d làm trên nhánh sau khi 0032 merge.
- **T9.2b Xong khi:** thêm `command_id uuid NOT NULL` + `UNIQUE(user_id, command_id)`; thêm `undo_revs_json jsonb` (ghi được cùng lúc `applied→undone`, trigger cập nhật cho phép đúng cột này); thêm nơi lưu cho StudyFilter và gỡ-câu nếu F2 chốt cần (xem Quyết định); upgrade/downgrade không mất dữ liệu; repo có `add`, `by_command_id`, `latest_open(session)`, `mark_undone` (khóa dòng `FOR UPDATE`). Mọi truy vấn lọc theo `user_id`.
- **T9.2c Xong khi:** `apply(user, command_id, session_id, ops_json)`: trùng `command_id` → trả bản ghi trước, không áp lần hai (kể cả hai yêu cầu song song: `INSERT … ON CONFLICT` hoặc bắt `IntegrityError`, rollback, đọc lại); kiểm id theo user trước khi áp (id lạ → `CommandRejected`, 404-giống-không-tồn-tại); khóa `FOR UPDATE` theo thứ tự id cố định để hai lệnh cùng thẻ không deadlock; nạp Snapshot đúng phạm vi id chạm; một bước lỗi → rollback cả lệnh và không có dòng log; ghi `inverse_json`; trả diff cấu trúc (động từ, đích, cũ, mới, số lượng) + `affected`; > 10 mục vẫn chạy; mọi ghi đi qua service chung của giao diện, cùng luật phiên bản ADR-0028 (rev thẻ = `unit.version`/`unit_revision`); AC4, AC9.
- **T9.2d Xong khi:** hoàn tác lệnh `applied` mới nhất của `screen_session_id`; `rev` đã đổi → `changed_after` kèm tên đối tượng, không ghi gì; thẻ chuẩn được hoàn tác bằng rev mới (không xóa lịch sử); thẻ do lệnh tạo → `discarded`; hoàn tác hai lần trùng → không hoàn tác thêm; không có redo; AC5.
- **T9.2e Xong khi:** `POST /v1/commands` (nhận `command_id`, ops đã parse hoặc dòng lệnh → gọi parse-command, cắt 8 s, 429 `quota_hard_cap` → mã tắt thanh lệnh), `POST /v1/commands/{command_id}/undo`; chưa xác minh email → 403 (theo `api/deps.py`); cách ly hai người dùng; hai lệnh đồng thời cùng thẻ (một thắng, kia `changed_after`/xung đột, không hỏng dữ liệu); core gửi `cards`/`sections` đúng thứ tự hiển thị (T9.1 Y1); lọc gợi ý áp trước khi xếp (móc `services/suggestions.py`, T7.10b); OpenAPI cập nhật.

## Dùng lại
`CommandRejected`/`op_from_json` `registry.py:32,338`; `Revert.expected_rev` `inverse.py:25`; `UserOwned` + `lock_drafts` `repositories/unit.py:173`; `practice.remove/readd` `services/practice.py:79-90`; fixture cách ly hai người dùng `tests/isolation.py`; mẫu đua `tests/races.py`.

## Test viết trước
| AC / quy tắc | Tên test | Đỏ khi |
|---|---|---|
| AC4 idempotent | `test_same_command_id_applies_once` | gửi hai lần mà log có 2 dòng hoặc diff lệch |
| AC4 song song cùng `command_id` | `test_concurrent_same_command_id_single_row` | tạo hai dòng / lỗi 500 |
| AC4 rollback | `test_failing_op_rolls_back_whole_command` | còn một thay đổi dở hoặc có dòng log |
| AC4 cách ly | `test_other_users_ids_rejected_no_leak` | id của người khác được áp hoặc lộ khác 404 |
| AC4 > 10 mục | `test_large_command_runs_and_reports_count` | bị chặn hoặc `affected` sai |
| AC5 rev | `test_undo_refused_when_card_changed_after` | hoàn tác vẫn chạy khi `rev` đã đổi |
| AC5 thứ tự | `test_undo_newest_first_only` | hoàn tác lệnh cũ khi lệnh mới còn mở |
| AC5 thẻ chuẩn | `test_undo_canonical_edit_appends_revision` | lịch sử bị xóa/ghi đè |
| AC5 đồng thời | `test_two_commands_same_card_one_wins` | cả hai áp, hoặc deadlock |
| AC6 | `test_no_destructive_op_registered` | có op xóa thẻ chuẩn/đặt lại FSRS |
| AC9 | `test_command_log_has_ops_diff_inverse` | thiếu `inverse_json` tính trước |
| bảo mật | `test_unverified_user_rejected` | tài khoản chưa xác minh áp được lệnh |
| F2 | `test_removed_question_stays_removed_after_cache_rebuild` | xóa `practice_state` rồi dựng lại thì câu hiện lại |

## Rủi ro và ca biên
- 🔴 Mất dữ liệu người học: rev lệch giữa nạp và ghi (kiểm lại `rev` ngay trong transaction đã khóa, không tin Snapshot cũ).
- 🔴 Idempotency: trùng `command_id` của **người khác** không được lộ; khóa unique gồm `user_id`.
- Hoàn tác: `undo_revs` phải ghi cùng lúc đánh dấu `undone`, nếu không lệnh cũ hơn kiểm `rev` sai.
- Prompt injection (ADR-0013/0014): ops chỉ mang id + số; văn bản (sửa nội dung, thêm thẻ) là dữ liệu, không bao giờ là lệnh; giới hạn độ dài text, `ops` tối đa N phần tử.
- Thứ tự khóa cố định chống deadlock; ghi nhật ký không chứa nội dung tài liệu ngoài text người dùng đã nhập.
- Gộp tất định không gọi LLM; gộp/tách chỉ thẻ nháp (đã có ở registry).

## Quyết định
| Quyết định | Lý do | Chốt bởi | Ngày |
|---|---|---|---|
| `command_id` thành cột + `UNIQUE(user_id, command_id)` ở migration 0032; `undo_revs_json` thêm cùng migration | bảng 0025 thiếu cả hai; lõi T9.2a cần | Coder (đề xuất) | 02/11 |
| Một service `services/commands.py` gọi các service/repo hiện có, không viết đường ghi riêng | ADR-0030 "cùng một đường" | Coder | 02/11 |
| Hoàn tác trả 409 `changed_after` kèm tên đối tượng; mã khác theo `CommandRejected.code` | khớp `undo.py:27-62` | Coder | 02/11 |
| **F2 `removed_at` (chọn C):** bảng chỉ-thêm `practice_removal_log(id,user_id,question_id,action removed\|readded,at,command_id NULL)`; `practice_state.removed_at` và `Question.in_practice` là cache dẫn xuất từ sự kiện mới nhất; nút và lệnh cùng gọi `practice.remove/readd`; hoàn tác ghi `readded`; trigger chặn UPDATE/DELETE; index (user_id,question_id,at DESC). Bỏ A (nút không qua command_log), bỏ B (không lưu câu chưa làm; `practice.remove` trả False khi chưa có `practice_state`). | ADR-0008:32, services/practice.py:79-83 | tech-expert | 02/11 |
| `study_filter(user_id,subject_id,mode,until,rev,updated_at)` PK (user_id,subject_id); hoàn tác lần đầu = xóa dòng | cần `rev` cho `expected_rev`; không dẫn xuất từ command_log | tech-expert | 02/11 |
| Phiên màn hoàn tác = `screen_session_id` web gửi, không theo thời gian; `latest_open` lọc user_id + screen_session_id; kiểm `UNIQUE(user_id,screen_session_id,seq)` ở 0025, thiếu thì thêm | cột có sẵn | tech-expert | 02/11 |
| Migration 0032 gộp: command_log (+command_id backfill gen_random_uuid(), +undo_revs_json, sửa trigger `command_log_guard` cho đặt cột này khi OLD NULL trong UPDATE applied->undone), practice_removal_log, study_filter. Không ADR mới; thêm đoạn "gỡ câu" vào ADR-0029; sửa PLAN dòng 736, 831 | một head | tech-expert | 02/11 |

## Câu hỏi mở
Không còn (F2, StudyFilter, phiên màn đã chốt ở bảng Quyết định). T9.2b thêm: 3 bảng/trigger nói trên; T9.2c ghi `practice_removal_log` qua `practice.remove/readd`.

## Sửa theo plan-review (vòng 1, 02/11; 6 điểm 🟠 đã vào kế hoạch, chốt bởi Coder)
- **P1 (rev nguồn thật):** T9.2b thêm `version int NOT NULL DEFAULT 1` cho `doc_section` và `question` (service tay và lệnh cùng tăng). Trước khi code T9.2c, `tech-expert` chốt ánh xạ `studied` (chỉ có `studied_weight`), `card_id/section_id` nhiều-nhiều (`question_unit`, `question_section`) và sửa đáp án kiểu retire-and-replace vào Snapshot; thao tác nào không ánh xạ được thì không đăng ký làm op hoàn tác được. T9.2c: `expected_rev` trong `inverse_json` lấy từ rev đọc lại trong DB sau khi ghi. Test: `inverse_json.expected_rev == knowledge_unit.version`; sửa tay mục rồi undo → 409 `changed_after`.
- **P2 (khóa khi undo):** khóa command_log của phiên rồi khóa các đối tượng trong inverse theo thứ tự id cố định (cùng thứ tự apply) trước khi nạp Snapshot và kiểm rev; ghi bằng `UPDATE … WHERE version = expected`, rowcount 0 → rollback `changed_after`. Test đua có barrier giữa kiểm rev và ghi.
- **P3 (undo theo command_id):** `POST /v1/commands/{command_id}/undo`: nạp dòng theo (user_id, command_id), `screen_session_id` lấy từ dòng, không từ client; đã `undone` → 200 trả kết quả cũ; không phải lệnh mở mới nhất của phiên → 409 `not_latest`. Test `test_undo_same_command_twice_does_not_undo_older`.
- **P4 (thứ tự idempotency):** `by_command_id(user)` trước; chưa có mới gọi parse-command NGOÀI transaction (không giữ khóa 8 s); sau đó mở transaction, khóa, áp, `INSERT … ON CONFLICT (user_id, command_id) DO NOTHING` (0 dòng → rollback, đọc lại). Lưu SHA-256 (raw_text, ops) (cột `payload_hash` trong 0032); cùng command_id khác payload → 409 `command_id_reused`. Test đếm lời gọi parse = 1.
- **P5 (test thêm):** `test_command_id_collision_across_users`, `test_undo_other_users_command_404`, `test_undo_unverified_rejected`, test hai người dùng cho `study_filter` và `practice_removal_log` (dùng `tests/isolation.py`).
- **P6 (log):** log/trace/`CommandRejected.detail` chỉ ghi command_id, số ops, loại op, affected, mã lỗi; `raw_text`, text trong ops, diff chỉ ở `command_log` và response cho chủ. Câu "ghi nhật ký không chứa nội dung…" ở mục Rủi ro thay bằng quy tắc này. Test caplog với chuỗi `BIMAT-xyz`.
- 🟡 nhận luôn: Y1 `ADD COLUMN command_id uuid NOT NULL DEFAULT gen_random_uuid()` rồi DROP DEFAULT (không UPDATE, tránh trigger); Y2 `practice_removal_log` dùng `append_only_refuse()`, thêm `seq` identity, index (user_id, question_id, seq DESC), command_id không FK; Y3 `study_filter` không DELETE khi hoàn tác: giữ dòng, `mode` NULL, tăng `rev` (tránh ABA; thay câu "xóa dòng" ở bảng Quyết định); Y4 bỏ UNIQUE thừa, thêm index (user_id, screen_session_id, seq DESC), `changed_after` giả là chấp nhận; Y5 một hàm validate (`op_from_json` + danh sách cố định) cho cả ops client lẫn LLM, ops không hợp lệ → 422.
- **Ước lượng lại:** T9.2b 2.5 h (thêm version cột + payload_hash + 2 bảng), T9.2c 3 h, T9.2d 2.5 h, T9.2e 2.5 h; mỗi cái ≤ 3 h. T9.2c cần tech-expert chốt ánh xạ P1 trước.
