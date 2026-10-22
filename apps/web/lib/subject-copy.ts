// The subject screens' sentences (DESIGN.md §6.8). "Ngày thi phải sau hôm nay." is DESIGN's; the
// format, empty-name and "Đã lưu." sentences were chosen by the user on 22/10 (plan K7). The
// rest are placeholders (data-copy="tam" where shown) listed in the PR for the user to approve.
export const SUBJECT_MESSAGES = {
  exam_date_not_in_future: "Ngày thi phải sau hôm nay.",
  exam_date_too_far: "Ngày thi cách quá xa (tối đa 2 năm). Kiểm tra lại năm nhé.",
  // {example} is the page's example date (risk register R24): a fixed year would turn into a
  // date core-api refuses once it passes.
  date_format: "Nhập ngày theo dạng ngày/tháng/năm, ví dụ {example}.",
  name_empty: "Nhập tên môn, ví dụ Mạng máy tính.",
  name_invalid: "Tên môn dài tối đa 200 ký tự.",
  subject_not_found: "Không tìm thấy môn này. Tải lại trang rồi thử lại.",
  saved: "Đã lưu.",
  unavailable: "Chưa gửi được. Kiểm tra kết nối rồi thử lại.",
} as const;

export type SubjectMessage = keyof typeof SUBJECT_MESSAGES;

/** A message as shown, with the example date in place (only date_format has one). */
export function subjectMessage(code: SubjectMessage, example: string): string {
  return SUBJECT_MESSAGES[code].replace("{example}", example);
}

/** The user's sentence (plan K7) with this example (R24, D12). */
export const dateFormatMessage = (example: string) => subjectMessage("date_format", example);

/** Sentences no document has yet: shown with data-copy="tam". */
export const PLACEHOLDER_MESSAGES = new Set<SubjectMessage>([
  "exam_date_too_far",
  "name_invalid",
  "subject_not_found",
]);
