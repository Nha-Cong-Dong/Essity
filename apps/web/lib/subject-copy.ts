// The subject screens' sentences (DESIGN.md §6.8). "Ngày thi phải sau hôm nay." is DESIGN's; the
// format, empty-name and "Đã lưu." sentences were chosen by the user on 22/10 (plan K7). The
// rest are placeholders (data-copy="tam" where shown) listed in the PR for the user to approve.
export const SUBJECT_MESSAGES = {
  exam_date_not_in_future: "Ngày thi phải sau hôm nay.",
  date_format: "Nhập ngày theo dạng ngày/tháng/năm, ví dụ 15/12/2026.",
  name_empty: "Nhập tên môn, ví dụ Mạng máy tính.",
  name_invalid: "Tên môn dài tối đa 200 ký tự.",
  subject_not_found: "Không tìm thấy môn này. Tải lại trang rồi thử lại.",
  saved: "Đã lưu.",
  unavailable: "Chưa gửi được. Kiểm tra kết nối rồi thử lại.",
} as const;

export type SubjectMessage = keyof typeof SUBJECT_MESSAGES;

/** Sentences no document has yet: shown with data-copy="tam". */
export const PLACEHOLDER_MESSAGES = new Set<SubjectMessage>(["name_invalid", "subject_not_found"]);
