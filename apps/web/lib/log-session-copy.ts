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
  // T4.13b: the notebook photos and note files. Codes are web's, core-api's or the browser's.
  note_unsupported: "Chỉ nhận ảnh JPG, PNG hoặc file PDF, TXT, MD.",
  note_empty: "File này trống.",
  note_too_big: "File lớn hơn 20 MB. Chọn file nhỏ hơn.",
  file_too_large: "File lớn hơn 20 MB. Chọn file nhỏ hơn.",
  storage_quota_exceeded: "Bạn đã dùng hết dung lượng cho ghi chú. Bỏ bớt file cũ hoặc thử lại sau.",
  too_many_notes: "Một buổi học chỉ nhận tối đa 20 file ghi chú.",
  bad_note: "File này bị lỗi khi chuẩn bị. Chọn lại file.",
  offline: "Mất kết nối. Kiểm tra mạng rồi chọn lại file.",
  upload_expired: "Liên kết tải đã hết hạn. Chọn lại file.",
  upload_failed: "Chưa tải được file này. Chọn lại file.",
  upload_incomplete: "Một file ghi chú chưa lên đến nơi. Bỏ file đó rồi chọn lại.",
  content_mismatch: "Một file ghi chú không đúng loại đã chọn. Bỏ file đó rồi chọn lại.",
  size_mismatch: "Một file ghi chú bị lỗi khi tải lên. Bỏ file đó rồi chọn lại.",
} as const;

export type LogMessage = keyof typeof LOG_MESSAGES;

/** The sentence for a failure code: anything unknown is "unavailable". */
export function logMessage(code: string): string {
  return Object.hasOwn(LOG_MESSAGES, code) ? LOG_MESSAGES[code as LogMessage] : LOG_MESSAGES.unavailable;
}
