// T7.12a: typed fixtures for /design-preview/session (no API).
import type { DocRef } from "@/lib/session-study/mention";

export const SUBJECT_NAME = "Mạng máy tính";
export const LONG_SUBJECT_NAME = "Kiến trúc máy tính và hệ điều hành nâng cao học kỳ hai năm hai ngành hai mươi sáu";
const LONG_WORD = "Kiếntrúcmáytínhvàhệđiềuhànhnângcaohọckỳhainămhaingànhaimươisáu_kếtthúc";

export const DOCS: DocRef[] = [
  { id: "d-textbook", name: "Giáo trình", role: "Giáo trình chính" },
  { id: "d-slide", name: "slide c3", role: "Slide" },
  { id: "d-notes", name: "Vở ghi 12-10", role: "Vở ghi" },
  { id: "d-exam", name: "Đề thi mẫu", role: "Đề thi" },
  { id: "d-long", name: `Tài liệu tên rất dài ${LONG_WORD}`, role: "Tham khảo" },
];

export type Suggestion = { kind: "section"; text: string; reason: string; pace: string } | { kind: "free"; text: string };

export const SUGGESTION: Suggestion = {
  kind: "section",
  text: "Nội dung học tập: 3.2 TCP flow control (tr. 52-58)",
  reason: "Phần kế tiếp trong đề cương. Còn 12 phần (86 trang), 20 ngày.",
  pace: "Phần 3.2 chưa học. Phần 3.1 đã xong hôm kia.",
};

export const NEXT_SUGGESTION: Suggestion = {
  kind: "section",
  text: "Tiếp theo nên học: phần 3.3 TCP congestion control (tr. 59-66)",
  reason: "Phần kế tiếp trong đề cương. Còn 11 phần (78 trang), 20 ngày.",
  pace: "Phần 3.2 vừa học xong.",
};

export const FREE_SUGGESTION: Suggestion = {
  kind: "free",
  text: "Buổi học tự do. Bài nộp không gắn phần đề cương.",
};

export type FileRow = {
  id: string;
  name: string;
  kind: "image" | "pdf" | "docx" | "pptx" | "text";
  state: "uploading" | "done" | "bad-type" | "too-big" | "net-error";
  percent?: number;
};

export const FILES: FileRow[] = [
  { id: "f1", name: "vo-ghi-trang-1.jpg", kind: "image", state: "done" },
  { id: "f2", name: `slide-chuong-3-${LONG_WORD}.pptx`, kind: "pptx", state: "uploading", percent: 40 },
  { id: "f3", name: "ghi-chu.exe", kind: "text", state: "bad-type" },
  { id: "f4", name: "scan-ca-quyen.pdf", kind: "pdf", state: "too-big" },
  { id: "f5", name: "vo-ghi-trang-2.jpg", kind: "image", state: "net-error" },
];

export type Scenario =
  | "empty"
  | "free"
  | "refused"
  | "files"
  | "processing"
  | "pending"
  | "failed"
  | "done"
  | "done-none";

export const SCENARIOS: { id: Scenario; label: string }[] = [
  { id: "empty", label: "Trống" },
  { id: "free", label: "Học tự do" },
  { id: "files", label: "Có file" },
  { id: "refused", label: "Phạm vi bị từ chối" },
  { id: "processing", label: "Đang đọc" },
  { id: "pending", label: "Hết lượt AI" },
  { id: "failed", label: "Không đọc được" },
  { id: "done", label: "Đã thêm thẻ" },
  { id: "done-none", label: "Chưa có thẻ" },
];
