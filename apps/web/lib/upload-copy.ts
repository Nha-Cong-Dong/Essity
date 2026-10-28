// T4.6: what the upload step says when a file is refused. Placeholder sentences (risk register
// R09): shown through a data-copy="tam" element in components/subjects/uploader.tsx until the user
// approves them. Codes are core-api's (T4.5), web's (offline, rate_limited, ...) or the browser's.
export const UPLOAD_MESSAGES: Record<string, string> = {
  not_pdf: "Chỉ nhận file PDF.",
  too_big: "File lớn hơn 100 MB. Chọn file nhỏ hơn.",
  empty: "File này trống.",
  unsupported_file_type: "Chỉ nhận file PDF.",
  invalid_filename: "Tên file không dùng được. Đổi tên rồi chọn lại.",
  file_too_large: "File lớn hơn 100 MB. Chọn file nhỏ hơn.",
  storage_quota_exceeded: "Bạn đã dùng hết 1 GB dung lượng tài liệu.",
  rate_limited: "Bạn đã tải quá 30 lần trong một giờ. Thử lại sau.",
  storage_full: "Kho lưu trữ đang đầy. Thử lại sau.",
  content_mismatch: "File này không phải PDF hợp lệ nên không nhận.",
  size_mismatch: "File bị lỗi khi tải lên. Chọn lại file.",
  upload_expired: "Liên kết tải đã hết hạn. Chọn lại file.",
  upload_incomplete: "File chưa lên đến nơi. Chọn lại file.",
  subject_not_found: "Không tìm thấy môn này. Tải lại trang rồi thử lại.",
  offline: "Mất kết nối. Kiểm tra mạng rồi chọn lại file.",
};

export const UPLOAD_FALLBACK = "Chưa tải được file này. Thử lại sau giây lát.";

export const uploadMessage = (code: string): string => UPLOAD_MESSAGES[code] ?? UPLOAD_FALLBACK;
