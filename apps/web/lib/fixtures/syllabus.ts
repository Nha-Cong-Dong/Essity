import type { UploadFile } from "@/lib/syllabus/roles";
import type { Source, SyllabusNode, Unit } from "@/lib/syllabus/tree";

// T7.5a: fixed data for /design-preview/syllabus. T7.5 replaces it with the T7.4 API. The shapes
// are a guess until T7.4 defines the endpoints (US-13 §9 #3).

export const SUBJECT = { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" };
export const MAIN_NAME = "Giáo trình Mạng máy tính (Kurose)";
export const TOTAL_PAGES = 820;

export type SyllabusState =
  | "ready"
  | "provisional"
  | "provisional-scan"
  | "extracting"
  | "empty-no-main"
  | "flat-pptx"
  | "editing"
  | "range-error"
  | "parent-panel"
  | "save-error"
  | "loading"
  | "error"
  | "long-titles"
  | "deep";

export const SYLLABUS_STATE_IDS: SyllabusState[] = [
  "ready", "provisional", "provisional-scan", "extracting", "empty-no-main", "flat-pptx", "editing",
  "range-error", "parent-panel", "save-error", "loading", "error", "long-titles", "deep",
];

export type UploadState =
  | "upload-empty"
  | "upload-files"
  | "upload-main-exists"
  | "upload-rename"
  | "upload-rejected"
  | "upload-uploading";

export const UPLOAD_STATE_IDS: UploadState[] = [
  "upload-empty", "upload-files", "upload-main-exists", "upload-rename", "upload-rejected", "upload-uploading",
];

export type SyllabusFixture = {
  mainName: string;
  source: Source;
  unit: Unit;
  total: number;
  nodes: SyllabusNode[];
  /** Short sentence in the "tạm" box: which of the three (chunk10, scan, flat deck). */
  notice: "chunk10" | "scan" | "flat" | null;
};

const node = (
  id: string,
  title: string,
  from: number,
  to: number,
  extra: Partial<SyllabusNode> = {},
): SyllabusNode => ({
  id, title, from, to, weight: to - from + 1, excluded: false, done: false, part: null, byHand: false, edited: false, children: [], ...extra,
});
const branch = (id: string, title: string, from: number, to: number, children: SyllabusNode[], extra: Partial<SyllabusNode> = {}) =>
  node(id, title, from, to, { children, ...extra });

const CHAPTER_1 = branch("1", "Chương 1 Tổng quan về mạng", 1, 44, [
  node("1.1", "1.1 Internet là gì", 1, 12, { done: true }),
  node("1.2", "1.2 Rìa mạng, lõi mạng và mạng truy cập", 13, 26, { done: true }),
  node("1.3", "1.3 Trễ, mất gói và thông lượng", 27, 44, { done: true }),
]);

const CHAPTER_2 = branch("2", "Chương 2 Tầng ứng dụng", 45, 98, [
  node("2.1", "2.1 Nguyên lý của ứng dụng mạng", 45, 54, { done: true }),
  node("2.2", "2.2 Web và HTTP", 55, 68, { part: [55, 60] }),
  node("2.3", "2.3 Thư điện tử trên Internet", 69, 78),
  node("2.4", "2.4 DNS", 79, 90),
  node("2.5", "2.5 Lập trình socket", 91, 98, { excluded: true }),
]);

const CHAPTER_3 = branch("3", "Chương 3 Tầng giao vận", 99, 190, [
  branch("3.1", "3.1 Dịch vụ tầng giao vận", 99, 120, [
    node("3.1.1", "3.1.1 Ghép kênh và phân kênh", 99, 110),
    node("3.1.2", "3.1.2 UDP", 111, 120),
  ]),
  node("3.2", "3.2 Truyền dữ liệu tin cậy", 121, 150),
  node("3.3", "3.3 TCP", 151, 175),
  node("3.4", "3.4 Kiểm soát tắc nghẽn", 176, 190),
]);

const CHAPTER_4 = branch("4", "Chương 4 Tầng mạng", 191, 260, [
  node("4.1", "4.1 Chuyển mạch gói", 191, 215),
  node("4.2", "4.2 Địa chỉ IP", 216, 238),
  node("4.3", "4.3 Định tuyến", 239, 260),
]);

const READY: SyllabusFixture = {
  mainName: MAIN_NAME,
  source: "bookmark",
  unit: "page",
  total: TOTAL_PAGES,
  nodes: [CHAPTER_1, CHAPTER_2, CHAPTER_3, CHAPTER_4],
  notice: null,
};

const TEXT_TITLES = [
  "Giới thiệu", "Khái niệm cơ bản", "Mô hình tham chiếu", "Các giao thức nền", "Phân tích hiệu năng",
  "Bảo mật cơ bản", "Quản trị mạng", "Ôn tập chương",
];
const chunk = (n: number) =>
  Array.from({ length: n }, (_, i) => {
    const from = i * 10 + 1;
    const to = from + 9;
    return node(`c${i + 1}`, `Trang ${from}–${to}`, from, to, i < 2 ? { done: true } : i === 2 ? { part: [21, 24] } : {});
  });

const PROVISIONAL: SyllabusFixture = {
  ...READY,
  source: "chunk10",
  nodes: chunk(12),
  total: 120,
  notice: "chunk10",
};

const SLIDES: SyllabusNode[] = Array.from({ length: 14 }, (_, i) =>
  node(`s${i + 1}`, `Slide ${i + 1}: ${TEXT_TITLES[i % TEXT_TITLES.length]}`, i + 1, i + 1, i < 3 ? { done: true } : {}),
);

const LONG_WORD = "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượng_kỳthi_tầnggiaovận";

const LONG: SyllabusFixture = {
  ...READY,
  mainName: "Giáo trình Mạng máy tính và truyền thông dữ liệu nâng cao, tái bản lần thứ tám, có chỉnh sửa",
  nodes: [
    branch("1", "Chương 1 Các mô hình và giao thức tầng giao vận trong mạng máy tính hiện đại: so sánh, đánh giá hiệu năng và ứng dụng thực tế", 1, 60, [
      node("1.1", `1.1 ${LONG_WORD}`, 1, 20, { done: true }),
      node("1.2", "1.2 Ặẫỡữ ẳằắ ỗ ộ ề ế ể: tiêu đề có nhiều dấu chồng nhau để thử chiều cao dòng", 21, 40, { part: [21, 30] }),
      node("1.3", "1.3 Mục đã bỏ khỏi đề cương thi nhưng có tiêu đề rất dài để thử nhãn không thi nằm gọn", 41, 60, { excluded: true }),
    ]),
    branch("2", `Chương 2 ${LONG_WORD}`, 61, 120, [
      node("2.1", "2.1 Một tiêu đề dài vừa phải để xuống dòng ở màn hình hẹp", 61, 90),
      node("2.2", "2.2 Ngắn", 91, 120),
    ]),
  ],
};

const DEEP_TITLES = ["Chương 5", "5.1", "5.1.1", "5.1.1.1", "5.1.1.1.1", "5.1.1.1.1.1"];
const deepNode = (level: number): SyllabusNode => {
  const id = DEEP_TITLES[level - 1];
  const from = 300 + level;
  const own = node(id, `${id} Tiêu đề của mục ở cấp ${level}, đủ dài để xuống dòng khi thụt sâu`, from, 330, level === 6 ? { part: [from, from + 3] } : {});
  return level === 6 ? own : { ...own, children: [deepNode(level + 1)] };
};
const DEEP: SyllabusFixture = {
  ...READY,
  nodes: [CHAPTER_1, { ...deepNode(1), id: "5" }],
};

export const FIXTURES: Record<"ready" | "provisional" | "provisional-scan" | "flat-pptx" | "long-titles" | "deep", SyllabusFixture> = {
  ready: READY,
  provisional: PROVISIONAL,
  "provisional-scan": { ...PROVISIONAL, notice: "scan" },
  "flat-pptx": {
    mainName: "Bài giảng Mạng máy tính (tuần 1–14).pptx",
    source: "heading",
    unit: "slide",
    total: 14,
    nodes: SLIDES,
    notice: "flat",
  },
  "long-titles": LONG,
  deep: DEEP,
};

/** The open panel a state starts with (the static preview cannot click its way there). */
export const PANEL_AT: Partial<Record<SyllabusState, { id: string; mode: "actions" | "edit"; from?: string; to?: string; error?: boolean; saveError?: boolean }>> = {
  editing: { id: "2.3", mode: "edit", from: "69", to: "78" },
  "range-error": { id: "2.3", mode: "edit", from: "66", to: "120", error: true },
  "parent-panel": { id: "2", mode: "actions" },
  "save-error": { id: "2.3", mode: "edit", from: "69", to: "80", saveError: true },
};

const f = (id: string, name: string, kind: UploadFile["kind"], role: UploadFile["role"], state: UploadFile["state"], extra: Partial<UploadFile> = {}): UploadFile => ({
  id, name, kind, role, state, ...extra,
});

export const UPLOAD_FILES: Record<Exclude<UploadState, "upload-empty">, { subjectHasMain: boolean; existingMain?: string; files: UploadFile[]; open?: string; rejected?: string[]; notice?: string }> = {
  "upload-files": {
    subjectHasMain: false,
    files: [
      f("a", "Giáo trình Mạng máy tính", "pdf", "main", "reading-toc"),
      f("b", "Đề thi các năm", "pdf", "bank", "ready", { chosen: true }),
      f("c", "Slide tuần 1-6", "pptx", "supplementary", "reading"),
      f("d", "Ảnh vở chương 2", "image", "supplementary", "ready"),
    ],
  },
  "upload-main-exists": {
    subjectHasMain: true,
    existingMain: MAIN_NAME,
    files: [f("a", "Giáo trình bản mới", "pdf", "supplementary", "ready")],
    open: "a",
  },
  "upload-rename": {
    subjectHasMain: true,
    files: [
      f("a", "Slide tuần 1-6", "pptx", "supplementary", "ready"),
      f("b", "Slide tuần 7-12", "pptx", "supplementary", "ready"),
    ],
  },
  "upload-rejected": {
    subjectHasMain: true,
    files: [
      f("a", "Slide tuần 1-6", "pptx", "supplementary", "ready"),
      f("b", "Ghi chú cũ", "docx", "supplementary", "partial", { unreadable: [12, 13, 40] }),
      f("c", "Đề thi 2024", "pdf", "bank", "failed"),
    ],
    rejected: ["Không nhận bai-giang.zip. App nhận PDF, DOCX, PPTX, JPG và PNG.", "Bộ ảnh cả học kỳ.pdf lớn quá. Chia nhỏ rồi tải lại."],
  },
  "upload-uploading": {
    subjectHasMain: false,
    files: [
      f("a", "Giáo trình Mạng máy tính", "pdf", "main", "uploading", { progress: 40 }),
      f("b", "Đề thi các năm", "pdf", "supplementary", "uploading", { progress: 15 }),
      f("c", "Slide tuần 1-6", "pptx", "supplementary", "ready"),
    ],
  },
};
