# T9.2 — core-api: áp lệnh và hoàn tác 🔴 (kế hoạch nhánh `t9.2-plan`)

> Chỉ kế hoạch. Ước 8–9 h, tách 4 sub-task ≤ 3 h (W10). Nguồn: PLAN.md:825-838, ADR-0030, ADR-0008:25-40, ADR-0029:22-30, spec US-18 AC4/5/6/8/9. Đã qua plan-review 2 vòng (6 🟠 vòng 1, 3 🟠 vòng 2, nay sửa tại chỗ) và `tech-expert.md`, `tech-expert-confirm.md`. Chỗ nào mâu thuẫn, bản này thắng.

## Trạng thái
| Bước | HEAD | Báo cáo cuối | Việc kế |
|---|---|---|---|
| Kế hoạch (vòng 3, sửa tại chỗ) | main 9fff3d2 | plan-review r2 fail → sửa; tech-expert xác nhận (tech-expert-confirm.md) | giao T9.2b (cần L1) |

## Hiện trạng
- Lõi thuần T9.2a: `domain/commands/apply.py:41`, `inverse.py:36-44` (`Revert.expected_rev`), `undo.py:27-62` (`nothing_to_undo|other_session|changed_after`), `registry.py:328,338` (`run_op`, `op_from_json`), `state.py` (Snapshot).
- `command_log` đã có ở 0025 (`db/models/command.py:27-60`), trigger `command_log_guard` (0025:44-62) chỉ cho `applied→undone`.
- Thiếu so với lõi: `command_id`, `payload_hash`, `undo_revs_json`; chỗ lưu StudyFilter; nguồn `in_practice`; `version` cho `doc_section`/`question`.
- Ánh xạ vào service hiện có: `OutlineService` (`services/outline.py:93`), `services/practice.py:79,86`, `repositories/unit.py`, `repositories/question.py`.

## Ánh xạ op → DB (tech-expert-confirm.md §1)
| Op | DB / rev | Hoàn tác |
|---|---|---|
| `section_exclude` | `doc_section.excluded` + `source='user'`; rev = `doc_section.version` | có |
| `section_mark` (studied) | suy ra từ `studied_weight` trên các lá của cây con; before-image `{lá: studied_weight}`; `undo_revs_json` liệt kê từng lá | có, trên lá |
| `section_set_pages` | đổi cả weight/studied_weight của anh em (`outline.py:185-199`) | **KHÔNG đăng ký** (before-image phải phủ cả tài liệu) |
| `question_set_answer` | `answer_text`+`answer_origin`; rev = `question.version` | có |
| `question_set_type` | `question.type_id`; rev = `question.version` | có |
| `question_remove` | `practice_removal_log` (hoàn tác ghi `readded`); rev = id lớn nhất của log theo (user, question), 0 khi chưa có | có |
| `question_relink` | nhiều-nhiều `question_unit`/`question_section` | **KHÔNG đăng ký**; Snapshot nạp chỉ-đọc |
| retire/replace | không phải op registry; trigger version làm undo `set_answer` lên câu đã retire → `changed_after` | không op |
| `study_filter` | bảng `study_filter`; rev | có |
| `card_*` | `unit`, `unit.version` (ADR-0028) | như thiết kế |

Quy tắc: `expected_rev` ghi vào `undo_revs_json` lấy bằng ĐỌC LẠI sau khi áp, trong cùng transaction (một op có thể UPDATE hai lần), không tính cộng.

## Kế hoạch: sub-task
| # | Sub-task | Ước | Touches | Cần L1 |
|---|---|---|---|---|
| T9.2b | Migration 0032 + repository | 2.5 h | `migrations/versions/0032_command_log_v2.py`, `db/models/{command,document,question}.py` (+model mới), `repositories/command_log.py`, `repositories/practice_removal.py`, `repositories/study_filter.py`, `tests/schema_v2/` | **Có** (một Alembic head; số 0032 kiểm lại BOARD) |
| T9.2c | Áp lệnh trong một transaction, idempotent | 3 h | `services/commands.py` (mới), `repositories/command_log.py`, `repositories/{unit,doc_section,question}.py` (thêm hàm nạp/ghi), `services/practice.py` (remove/readd ghi log + khóa question), tests | Không |
| T9.2d | Hoàn tác theo command_id | 2.5 h | `services/commands.py`, `repositories/command_log.py`, tests | Không |
| T9.2e | API + cách ly/chưa xác minh/đồng thời + móc lọc gợi ý | 2.5 h | `api/commands.py`, đăng ký router, `services/suggestions.py` (móc lọc), `tests/api/`, OpenAPI | **Có**: sinh lại `packages/api-client` sau merge |

Thứ tự tuần tự T9.2b → c → d → e. Không cần thêm `outline.py`/`practice_grading.py` vào touches T9.2c vì version tăng bằng trigger.

- **T9.2b Xong khi:**
  - `command_log`: thêm `command_id uuid NOT NULL` (ADD COLUMN … DEFAULT `gen_random_uuid()` rồi DROP DEFAULT, không UPDATE vì trigger chặn), `UNIQUE(user_id, command_id)`, `payload_hash char(64) NOT NULL`, `undo_revs_json jsonb NULL`; sửa `command_log_guard` cho đặt `undo_revs_json` khi OLD NULL trong UPDATE `applied→undone`; index `(user_id, screen_session_id, seq DESC)`; không thêm UNIQUE theo seq.
  - `doc_section.version` và `question.version` (`int NOT NULL DEFAULT 1`) tăng bằng trigger BEFORE UPDATE (ghi đè `NEW.version := OLD.version+1` khi cột nội dung đổi; bỏ qua giá trị client gửi). Nội dung `doc_section`: title, unit, weight, studied_weight, excluded, source, first_page, last_page, parent_id, ord. Nội dung `question`: level, prompt, reference_answer, rubric, status, content_hash, type_id, answer_text, answer_origin, quality_status. Loại: id, user_id, subject_id, document_id, timestamps, run_id, source, bank_*, generation_id, unit_rev, version. Test chặn trôi: mọi cột của model nằm trong "nội dung" hoặc "loại".
  - Test: mọi UPDATE doc_section/question (qua `OutlineService` sửa mục/studied, điền đáp án `practice_grading.py:139`, retire, replace) làm tăng `version`; sửa tay rồi hoàn tác bị từ chối (`changed_after`, kiểm ở T9.2d).
  - `practice_removal_log(id bigint identity, user_id, question_id, action removed|readded, at, command_id NULL không FK)`: chỉ-thêm bằng `append_only_refuse()` (0008), FK question NO ACTION, index `(user_id, question_id, id DESC)`. `removed_at`/`in_practice` là cache từ sự kiện mới nhất; rebuild (`repositories/practice.py:168-209`) đọc log.
  - `study_filter(user_id, subject_id, mode NULL, until, rev int NOT NULL DEFAULT 1, updated_at)` PK `(user_id, subject_id)`; hoàn tác KHÔNG DELETE: đặt `mode` NULL và tăng `rev` (tránh ABA).
  - Repo `command_log`: `add`, `by_command_id(user)`, `latest_open(user, session)`, `mark_undone` (FOR UPDATE); mọi truy vấn lọc `user_id`. Downgrade khôi phục trigger 0025 và bỏ cột/bảng mới (không bảo đảm giữ dữ liệu của chúng).
  - Ghi đoạn "gỡ câu" và hai op không đăng ký vào ADR-0029 (docs, orchestrator).
- **T9.2c Xong khi:** `apply(user, command_id, session_id, request)`:
  - Thứ tự: tính `payload_hash` (SHA-256 JSON chuẩn hóa `{raw_text NFC không trim, screen_session_id uuid thường, ops client|null}`, sort_keys, gọn, UTF-8, không gồm command_id) trước parse; `by_command_id(user)` → có: so hash, bằng → 200 trả diff đã lưu, KHÔNG gọi parse; khác → 409 `command_id_reused`. Chưa có → gọi parse-command NGOÀI transaction (không giữ khóa); rồi mở transaction.
  - Một hàm validate chung (`op_from_json` + danh sách op cố định) cho ops client và LLM; op lạ/không đăng ký → 422.
  - Kiểm id theo user trước khi áp (id lạ → `CommandRejected`, giống 404, không lộ). Khóa theo thứ tự chung (loại, id): command_log, rồi `doc_section < question < study_filter < unit`, id tăng dần; `study_filter` chưa có dòng khóa bằng `pg_advisory_xact_lock(hashtextextended('study_filter:'||user||':'||subject,0))`, rev=0 khi vắng. `practice.remove/readd` (nút và lệnh) cũng khóa dòng question trước khi INSERT log. Một hàm sắp thứ tự dùng chung apply/undo.
  - Ghi: `INSERT … ON CONFLICT (user_id, command_id) DO NOTHING`; 0 dòng → rollback, đọc lại. Một bước lỗi → rollback cả lệnh, không có dòng log. `inverse_json` tính trước; `undo_revs_json` theo quy tắc đọc lại. Trả diff cấu trúc (động từ, đích, cũ, mới, số lượng) + `affected`; > 10 mục vẫn chạy. Cùng đường ghi với giao diện (ADR-0028 cho thẻ). Log/trace/`CommandRejected.detail` chỉ chứa command_id, số ops, loại op, affected, mã lỗi; `raw_text`/text/diff chỉ ở `command_log` và response cho chủ. AC4, AC8, AC9.
- **T9.2d Xong khi:** `undo(user, command_id)`:
  - Nạp dòng theo `(user_id, command_id)`; `screen_session_id` lấy từ dòng, không từ client. Đã `undone` → 200 trả kết quả cũ, không hoàn tác thêm. Không phải lệnh `applied` mới nhất của phiên → 409 `not_latest`.
  - Khóa theo thứ tự chung (command_log của phiên, rồi đối tượng trong inverse), rồi nạp Snapshot và kiểm rev trong cùng transaction; ghi bằng `UPDATE … WHERE version = expected`, rowcount 0 → rollback `changed_after`. `in_practice`: rev = id lớn nhất của `practice_removal_log` kiểm sau khi khóa dòng question.
  - `rev` đã đổi (kể cả sửa tay) → `changed_after` kèm tên đối tượng, không ghi gì (`changed_after` giả khi lệnh khác phiên đã hoàn tác là chấp nhận được). Thẻ chuẩn hoàn tác bằng rev mới (không xóa lịch sử); thẻ do lệnh tạo → `discarded`; `mark_undone` ghi `undo_revs_json` cùng UPDATE; không redo; AC5.
- **T9.2e Xong khi:** `POST /v1/commands` (nhận `command_id`, `screen_session_id`, dòng lệnh hoặc ops đã parse), `POST /v1/commands/{command_id}/undo`; parse cắt 8 s, 429 `quota_hard_cap` → mã tắt thanh lệnh; chưa xác minh email → 403 (`api/deps.py`); cách ly hai người dùng; hai lệnh đồng thời cùng thẻ (một thắng, kia `changed_after`/xung đột); core gửi `cards`/`sections` đúng thứ tự hiển thị (T9.1 Y1); lọc gợi ý áp trước khi xếp (móc `services/suggestions.py`, T7.10b); OpenAPI cập nhật.

## Dùng lại
`CommandRejected`/`op_from_json` `registry.py:32,338`; `Revert.expected_rev` `inverse.py:25`; `UserOwned` + `lock_drafts` `repositories/unit.py:173`; `practice.remove/readd` `services/practice.py:79-90`; `tests/isolation.py`; `tests/races.py`.

## Test viết trước
| AC / quy tắc | Tên test | Đỏ khi |
|---|---|---|
| AC4 idempotent | `test_same_command_id_applies_once` | log có 2 dòng hoặc diff lệch |
| AC4/AC8 | `test_retry_same_command_id_one_parse_call` | gửi hai lần cùng raw_text mà lời gọi parse ≠ 1 hoặc trả 409 |
| AC4 | `test_command_id_reused_different_payload_409` | khác payload mà trả diff cũ |
| AC4 song song | `test_concurrent_same_command_id_single_row` | hai dòng hoặc 500 |
| AC4 rollback | `test_failing_op_rolls_back_whole_command` | còn thay đổi dở hoặc có dòng log |
| AC4 cách ly | `test_other_users_ids_rejected_no_leak` | id người khác được áp hoặc lộ khác 404 |
| AC4 cách ly | `test_command_id_collision_across_users` | B nhận diff của A (bỏ `user_id` trong `by_command_id` mà vẫn xanh) |
| AC4 | `test_large_command_runs_and_reports_count` | bị chặn hoặc `affected` sai |
| AC4 | `test_unregistered_op_422` | op ngoài danh sách được chạy |
| version | `test_update_doc_section_question_bumps_version` | UPDATE qua service tay không tăng version |
| version | `test_model_columns_classified_for_version_trigger` | cột mới chưa phân loại |
| P1 | `test_inverse_expected_rev_matches_db_version` | `expected_rev` ≠ `version` thật sau khi áp |
| AC5 rev | `test_undo_refused_when_manually_edited_after` | sửa tay (OutlineService) rồi undo vẫn chạy |
| AC5 thứ tự | `test_undo_newest_first_only`, `test_undo_same_command_twice_does_not_undo_older` | undo C2 hai lần hoàn tác C1 |
| AC5 thẻ chuẩn | `test_undo_canonical_edit_appends_revision` | lịch sử bị xóa/ghi đè |
| AC5 đua | `test_undo_race_with_manual_edit_one_409` | barrier giữa kiểm rev và ghi; bản sửa tay mất |
| AC5 đồng thời | `test_two_commands_same_card_one_wins` | cả hai áp, hoặc deadlock |
| khóa | `test_apply_vs_undo_lock_order_no_deadlock` | deadlock |
| AC5 | `test_undo_other_users_command_404` | đổi dữ liệu hoặc khác 404 |
| bảo mật | `test_unverified_user_rejected`, `test_undo_unverified_rejected` | chưa xác minh áp/hoàn tác được |
| F2 | `test_removed_question_stays_removed_after_cache_rebuild` | xóa `practice_state` (kể cả câu chưa làm) rồi câu hiện lại |
| F2 | `test_button_and_command_remove_write_same_log_row`, `test_undo_remove_writes_readded` | khác dòng log / không ghi readded |
| F2 | `test_in_practice_rev_detects_manual_readd` | lệnh gỡ, tay thêm lại rồi gỡ, undo vẫn ghi đè |
| cách ly | `test_study_filter_and_removal_log_isolated_two_users` | rò giữa hai người dùng |
| study_filter | `test_study_filter_undo_keeps_row_bumps_rev` | DELETE làm rev quay về 1 (ABA) |
| AC6 | `test_no_destructive_op_registered` (cả `section_set_pages`, `question_relink` không đăng ký) | có op xóa thẻ chuẩn/đặt lại FSRS |
| AC9 | `test_command_log_has_ops_diff_inverse` | thiếu `inverse_json` |
| P6 | `test_logs_and_errors_do_not_contain_raw_text` (chuỗi `BIMAT-xyz`) | chuỗi xuất hiện trong log hoặc body lỗi |

## Rủi ro và ca biên
- 🔴 Mất dữ liệu học: rev lệch giữa nạp và ghi → kiểm lại rev trong transaction đã khóa, ghi `WHERE version = expected`.
- 🔴 Idempotency: `command_id` trùng của người khác không lộ; unique gồm `user_id`; hash khác → 409.
- Prompt injection (ADR-0013/0014): ops chỉ mang id + số; text là dữ liệu; giới hạn độ dài text và số ops tối đa N.
- Deadlock: một thứ tự khóa (loại, id) chung apply/undo.
- Gộp tất định, không gọi LLM lần hai; gộp/tách chỉ thẻ nháp.

## Quyết định
| Quyết định | Lý do | Chốt bởi | Ngày |
|---|---|---|---|
| Rủi ro T8.3 F2: phương án C, bảng chỉ-thêm `practice_removal_log` (id identity, user_id, question_id, action, at, command_id NULL không FK); `removed_at`/`in_practice` là cache dẫn xuất; nút và lệnh cùng gọi `practice.remove/readd`; hoàn tác ghi `readded`; bỏ A (nút không qua command_log) và B (không lưu câu chưa làm) | ADR-0008:32; `services/practice.py:79-83` | tech-expert | 02/11 |
| `study_filter` bảng riêng có `rev`; hoàn tác giữ dòng (mode NULL, tăng rev), không DELETE | tránh ABA (reviewer Y3) | tech-expert + reviewer | 02/11 |
| Phiên hoàn tác = `screen_session_id` lưu trong dòng log (không do client gửi lúc undo, không theo thời gian); index `(user_id, screen_session_id, seq DESC)`, không UNIQUE thừa | cột có sẵn từ 0025 | tech-expert + reviewer | 02/11 |
| Undo theo `command_id`; đã undone → 200 cũ; không mới nhất → 409 `not_latest` | chống undo nhầm lệnh cũ (P3) | reviewer | 02/11 |
| `version` bằng trigger BEFORE UPDATE trên doc_section/question; `expected_rev` đọc lại sau khi áp | phủ mọi đường ghi tay (R2-1) | tech-expert | 02/11 |
| Không đăng ký `section_set_pages` và `question_relink` (không hoàn tác được) | before-image phải phủ cả tài liệu / không có rev cho tập liên kết | tech-expert | 02/11 |
| `payload_hash` = SHA-256 thân request nhận được, tính trước parse, không gồm ops LLM; parse ngoài transaction | retry hợp lệ không vỡ AC4/AC8 (R2-2) | tech-expert | 02/11 |
| rev của `in_practice` = id lớn nhất `practice_removal_log` theo (user, question) | R2-Y1 | tech-expert | 02/11 |
| Thứ tự khóa chung (loại, id): command_log, doc_section, question, study_filter (advisory lock nếu chưa có dòng), unit | R2-Y2 | tech-expert | 02/11 |
| Migration 0032 gộp tất cả mục trên; không ADR mới, thêm đoạn vào ADR-0029; sửa PLAN dòng 736, 831 (orchestrator) | một head | tech-expert | 02/11 |
| Một `services/commands.py` gọi service/repo hiện có, không có đường ghi riêng | ADR-0030 | Coder | 02/11 |
| Quy tắc log: chỉ command_id, số ops, loại op, affected, mã lỗi | ADR-0013 (P6) | reviewer | 02/11 |

## Câu hỏi mở
Không còn.
