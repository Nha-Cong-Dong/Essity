# tech-expert T9.2: chốt cột 0032 (02/11)

## (1) Ánh xạ Snapshot -> DB (registry.py:245-295)
| Op | DB | Hoàn tác |
|---|---|---|
| section_exclude | doc_section.excluded (+source='user', outline.py:206-208). Before-image: (excluded, source). rev = doc_section.version | có |
| section_mark (studied) | Section.studied là SUY RA: doc_section chỉ có studied_weight (outline.py:200-203, ghi trên lá). Service mở rộng mục thành các lá của cây con; before-image = {lá: studied_weight}; undo_revs_json liệt kê từng lá (version) | có, trên lá |
| section_set_pages | first_page/last_page + reweigh đổi weight/studied_weight của cả anh em (outline.py:185-199) | KHÔNG đăng ký (before-image phải phủ cả tài liệu). Ghi rõ trong bảng Quyết định |
| question_set_answer | Snapshot.answer = answer_text + answer_origin ('user'); before-image cả hai (CHECK answer_text_with_origin: cùng NULL được). reference_answer KHÔNG phải đáp án này: đổi nó = retire-and-replace (id mới, question.py:131), không phải op | có (answer_text) |
| question_set_type | question.type_id | có |
| question_remove | practice_removal_log (undo ghi readded) | có |
| question_relink (card_id/section_id) | nhiều-nhiều question_unit/question_section, Snapshot một-giá-trị | KHÔNG đăng ký (không có rev cho tập liên kết). Snapshot nạp chỉ-đọc |
| retire / replace | không phải op của registry | không op; nhưng trigger (2) làm undo set_answer lên câu đã retire trả 409 changed_after |
| study_filter | bảng study_filter, rev | có; lần đầu undo = xóa dòng |
| card_* | unit, unit.version (ADR-0028) | như plan |
Quy tắc: rev ghi vào undo_revs_json lấy bằng ĐỌC LẠI sau apply trong cùng transaction (một op có thể UPDATE 2 lần, version tăng 2), không tính cộng.

## (2) version bằng trigger BEFORE UPDATE (0032)
Cột `version int NOT NULL DEFAULT 1` trên doc_section và question. Trigger: nếu (cột nội dung) IS DISTINCT FROM giữa OLD/NEW thì NEW.version := OLD.version + 1 (bỏ qua tăng tay của client: luôn ghi đè NEW.version). Chạy trong cùng UPDATE nên `UPDATE ... WHERE version = expected` vẫn đúng ở READ COMMITTED (hàng đã khóa, điều kiện đánh giá lại).
- doc_section nội dung: title, unit, weight, studied_weight, excluded, source, first_page, last_page, parent_id, ord. (outline.py:195-205 ghi weight, studied_weight, first/last_page, source, excluded: phủ.)
- question nội dung: level, prompt, reference_answer, rubric, status, content_hash, type_id, answer_text, answer_origin, quality_status. (practice_grading.py:139-143 ghi answer_text/answer_origin: phủ; retire() đổi status: phủ; replace() retire hàng cũ: phủ.)
- Loại: id, user_id, subject_id, document_id, timestamps, run_id, source, bank_*, generation_id, unit_rev, version.
- Test chặn trôi: test schema liệt kê mọi cột của model, mỗi cột phải nằm trong "nội dung" hoặc danh sách loại (cột mới thêm sau mà quên thì đỏ). Test: OutlineService.set studied/sửa mục, practice_grading điền đáp án, retire, replace -> version tăng; sửa tay rồi undo -> 409 changed_after.
- Không cần thêm outline.py/practice_grading.py vào touches T9.2c.

## (3) rev của in_practice
rev = id (bigint identity, đóng vai seq) lớn nhất của practice_removal_log theo (user_id, question_id); 0 khi chưa có. Kiểm trong transaction undo SAU khi khóa dòng question (FOR UPDATE). Bắt buộc: practice.remove/readd (nút và lệnh) cũng khóa dòng question trước khi INSERT log, nếu không có race giữa kiểm và ghi.

## (4) Thứ tự khóa chung apply/undo
Một đường duy nhất: command_log (undo: dòng theo (user_id, command_id)) trước; rồi đối tượng sắp theo (tên bảng: doc_section < question < study_filter < unit, rồi id tăng dần). study_filter có thể chưa có dòng: khóa bằng pg_advisory_xact_lock(hashtextextended('study_filter:'||user||':'||subject,0)) ở đúng vị trí, rev=0 khi vắng. Apply cũng sắp theo thứ tự này trước khi UPDATE. Một hàm dùng chung, test barrier cả apply vs undo lẫn undo vs undo.

## (5) payload_hash
SHA-256 của thân request NHẬN ĐƯỢC, tính trước parse/LLM: JSON chuẩn hóa {raw_text (NFC, không trim), screen_session_id (uuid chữ thường), ops: ops client hoặc null}, sort_keys, separators gọn, UTF-8. Không gồm command_id. ops sau parse lưu riêng ở ops_json. Retry cùng command_id: thấy dòng -> so hash -> bằng: 200 trả diff đã lưu, không gọi parse; khác: 409 command_id_reused.
- R2-2: ĐÓNG nếu plan sửa theo đây (test: 2 POST cùng raw_text, parse gọi 1 lần).
- R2-1: ĐÓNG nếu 0032 có trigger + cột như (2), "Xong khi" T9.2b thêm "mọi UPDATE doc_section/question tăng version" và bảng Quyết định ghi 2 op không đăng ký ở (1).
- R2-3: KHÔNG tự đóng bằng xác nhận này; chỉ đóng khi Coder sửa tại chỗ "Xong khi" T9.2b/d, bảng Quyết định (plan.md:55,64-66) và thêm 10 test. Cũng thêm: R2-Y1 đóng bởi (3), R2-Y2 đóng bởi (4).
Cột 0032 cuối: command_log(+command_id, +payload_hash, +undo_revs_json, sửa trigger, index (user_id, screen_session_id, seq DESC)); doc_section.version; question.version; practice_removal_log(id identity, ...); study_filter(rev). Không ADR mới; ghi 2 op không đăng ký vào đoạn ADR-0029.
