# D1-SELFTEST-CORE bugs (account selftest-d1@example.com, build of main bf13adf9, web :3100)

| ID | Màn / bước | Mong đợi | Thực tế | Ảnh | Mức | Trạng thái |
|---|---|---|---|---|---|---|
| B-01 | glyph mây (logo sidebar, mọi màn) | mây hồng nguyên, viền tối | 2 nêm trắng nhỏ dưới vành mũ (khe giữa các cụm mây lộ viền trắng của mũ) | ev/zoom-logo-light.png | 🟡 | FIXED (patch hồng under-brim + test mascot) |
| B-02 | seed: `cli_review_account` tạo tài khoản thứ 2 | chạy với email khác | UsernameTakenError: username cố định `xstkreview`, không có cờ | - | 🟡 | FIXED (`--username` + test) |
| B-03 | /review/[id], thẻ đầu | câu hỏi hiện ngay | khung trống ~4 s (chỉ nút Dừng tại đây) rồi mới hiện câu | ev/review-d-10.png | 🟡 | OPEN (không sửa, hackathon) |
| B-04 | /subjects/[id] 1440 | trang cao ~1300 | cuộn tài liệu cao 4939 px: cây đề cương trong thẻ phải bị cắt nhưng phần tràn vẫn tính vào chiều cao trang, thừa nền hồng | ev/subject-d.png | 🟡 | OPEN |
| B-05 | inspect FAIL cũ (command-bar, subjects, today, review: heavy-shadow, h1 40px, headline-lines) | 0 FAIL | chưa chạy lại/sửa | - | 🟡 | OPEN (hackathon) |
| B-06 | verify-screens, quét tối, quên mật khẩu/đăng ký | - | bỏ theo lệnh hackathon 20:00 | - | - | OPEN (chưa kiểm) |

Đã đi tay (1440+390 sáng, 1440 tối cho today/subjects/stats): đăng nhập, hôm nay (Tiếp tục phiên dở), môn học, chi tiết môn, thống kê, phiên ôn 13 câu tới màn kết thúc (cả 1440 và 390): chạy được, không lỗi console/HTTP.
