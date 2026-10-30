// T7.12a: typed fixtures for /design-preview/session (no API). T7.12 swaps them for core-api data.
import type { Anchor, Draft } from "@/lib/session-study/drafts";
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
  text: "Hôm nay nên học: mục 3.2 TCP flow control (tr. 52-58)",
  reason: "Mục kế tiếp trong đề cương. Còn 12 mục (86 trang), 20 ngày.",
  pace: "Mục 3.2 chưa học. Mục 3.1 đã xong hôm kia.",
};

export const NEXT_SUGGESTION: Suggestion = {
  kind: "section",
  text: "Tiếp theo nên học: mục 3.3 TCP congestion control (tr. 59-66)",
  reason: "Mục kế tiếp trong đề cương. Còn 11 mục (78 trang), 20 ngày.",
  pace: "Mục 3.2 vừa học xong.",
};

export const FREE_SUGGESTION: Suggestion = {
  kind: "free",
  text: "Buổi học tự do. Bài nộp không gắn mục đề cương.",
};

const quote = (id: string, kind: Anchor["kind"], label: string, text: string): Anchor => ({ id, kind, label, quote: text });

export const DRAFTS: Draft[] = [
  {
    id: "c1",
    title: "Cửa sổ trượt",
    summary: "Bên nhận báo cửa sổ nhận; bên gửi không gửi quá số byte cửa sổ cho phép.",
    section: "3.2",
    anchors: [
      quote("a1", "document", "Giáo trình · tr. 52", "Bên gửi giữ số byte chưa được xác nhận không vượt quá rwnd."),
      quote("a2", "notes", "Vở ghi 12-10", "rwnd = vùng đệm trống của bên nhận"),
      quote("a3", "document", "slide c3 · tr. 12", "Receive window được gửi kèm mỗi ACK."),
    ],
    origin: "ai",
    status: "draft",
    version: 1,
    conflict: null,
    source: "both",
  },
  {
    id: "c2",
    title: "Cửa sổ nhận bằng 0",
    summary: "Khi cửa sổ nhận bằng 0, bên gửi dừng và gửi gói thăm dò nhỏ để biết khi nào có chỗ.",
    section: "3.2",
    anchors: [quote("a4", "document", "Giáo trình · tr. 55", "Gói thăm dò chứa 1 byte dữ liệu.")],
    origin: "ai",
    status: "draft",
    version: 1,
    conflict: null,
    source: "document",
  },
  {
    id: "c3",
    title: `Kiểm soát lưu lượng khác kiểm soát tắc nghẽn ${LONG_WORD}`,
    summary: "Lưu lượng bảo vệ bên nhận; tắc nghẽn bảo vệ mạng. Hai cơ chế dùng hai cửa sổ khác nhau.",
    section: null,
    anchors: [quote("a5", "notes", "Vở ghi 12-10", "flow control ≠ congestion control")],
    origin: "ai",
    status: "draft",
    version: 1,
    conflict: null,
    source: "notes",
  },
];

/** Many cards, for the layout test: 20 cards, the long title among them. */
export const MANY_DRAFTS: Draft[] = Array.from({ length: 20 }, (_, i) => ({
  ...DRAFTS[i % DRAFTS.length],
  id: `m${i + 1}`,
  anchors: DRAFTS[i % DRAFTS.length].anchors.map((a) => ({ ...a, id: `m${i + 1}-${a.id}` })),
}));

export const SERVER_VERSION: Draft = { ...DRAFTS[0], summary: "Bản mới từ thiết bị khác: bên nhận báo cửa sổ nhận.", version: 2 };

export const PARTIAL_NOTE = "Không đọc được trang 4 (ảnh mờ). Các trang còn lại vẫn được xử lý.";

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
  | "partial"
  | "review"
  | "conflict"
  | "many"
  | "empty-review"
  | "save-error"
  | "saved"
  | "saved-partial"
  | "saved-free"
  | "resume";

export const SCENARIOS: { id: Scenario; label: string }[] = [
  { id: "empty", label: "Trống" },
  { id: "free", label: "Học tự do" },
  { id: "files", label: "Có file" },
  { id: "refused", label: "Phạm vi bị từ chối" },
  { id: "processing", label: "Đang đọc" },
  { id: "pending", label: "Hết lượt AI" },
  { id: "failed", label: "Không đọc được" },
  { id: "partial", label: "Đọc một phần" },
  { id: "review", label: "Duyệt thẻ" },
  { id: "conflict", label: "Thẻ lệch (409)" },
  { id: "many", label: "20 thẻ" },
  { id: "empty-review", label: "Chưa tách được" },
  { id: "save-error", label: "Lỗi lưu" },
  { id: "saved", label: "Sau khi lưu" },
  { id: "saved-partial", label: "Sau lưu (một phần)" },
  { id: "saved-free", label: "Sau lưu (tự do)" },
  { id: "resume", label: "Tiếp tục" },
];
