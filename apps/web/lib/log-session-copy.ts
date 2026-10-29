// T4.13a: the words of "Ghi buổi học" that docs/design/screens-html/screens/log-session.html does
// not hold. Every one is a placeholder (data-copy="tam", risk register R09) until the user
// approves it; the ones in the mockup are written where they are drawn.

export const LOG_MESSAGES = {
  empty: "Kể một câu về buổi học trước khi gửi.",
  unavailable: "Chưa gửi được. Câu của bạn vẫn ở đây, bạn gửi lại nhé.",
  rate_limited: "Bạn gửi hơi nhanh. Chờ một lát rồi gửi lại nhé.",
  subject_not_found: "Không tìm thấy môn này. Tải lại trang rồi thử lại.",
  save_failed: "Chưa lưu được. Bấm Lưu lại nhé.",
  document: "Chọn một tài liệu.",
  pages: "Nhập số trang, ví dụ 43.",
  order: "Trang đến phải sau hoặc bằng trang từ.",
  beyond: "Tài liệu này không có nhiều trang đến vậy.",
} as const;

export type LogMessage = keyof typeof LOG_MESSAGES;

/** The sentence for a failure code: anything unknown is "unavailable". */
export function logMessage(code: string): string {
  return Object.hasOwn(LOG_MESSAGES, code) ? LOG_MESSAGES[code as LogMessage] : LOG_MESSAGES.unavailable;
}

/** What a failed save says: a card that moved on (404/409/422) reads the same as a dropped line. */
export function saveMessage(code: string): string {
  return code === "rate_limited" ? LOG_MESSAGES.rate_limited : LOG_MESSAGES.save_failed;
}
