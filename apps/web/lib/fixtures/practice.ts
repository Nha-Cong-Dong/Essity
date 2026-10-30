import type { PracticeQuestion, Timing } from "@/lib/practice";
import type { Result } from "@/lib/review-client";

// T8.7a: fixed data for /design-preview/practice. T8.7 replaces it with the T8.2-T8.6 API.
// The busiest state has one unbroken long type name and a long question summary.

export const LONG_TYPE = "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượng_kỳthi";
export const SUBJECT = { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" };

export type PracticeGroup = {
  id: string;
  name: string;
  /** The type was suggested by the AI and not yet edited or used: a pencil "gợi ý" (§6.12). */
  suggested: boolean;
  mastery: { score: number; attempts: number };
  timing: Timing;
  questions: PracticeQuestion[];
};

export type Candidate = { id: string; text: string; kind: string; cardLabel: string };
export type StudiedSection = { id: string; label: string; studied: boolean };

export type PracticeState =
  | "home"
  | "imported"
  | "no-bank"
  | "importing"
  | "empty-ready"
  | "candidates"
  | "no-candidates"
  | "quota"
  | "removed"
  | "result"
  | "loading"
  | "error";

export const PRACTICE_STATE_IDS: PracticeState[] = [
  "home", "imported", "no-bank", "importing", "empty-ready", "candidates", "no-candidates", "quota",
  "removed", "result", "loading", "error",
];

const q = (
  number: number,
  summary: string,
  status: PracticeQuestion["status"],
  extra: Partial<PracticeQuestion> = {},
): PracticeQuestion => ({
  id: `q${number}`,
  number,
  summary,
  origin: "bank",
  status,
  answerSource: "bank",
  practiced: false,
  mastered: false,
  ...extra,
});

export const GROUPS: PracticeGroup[] = [
  {
    id: "g1",
    name: LONG_TYPE,
    suggested: false,
    mastery: { score: 7, attempts: 10 },
    timing: { kind: "faster", refMinutes: 3 },
    questions: [
      q(11, "So sánh TCP và UDP về độ tin cậy, kiểm soát luồng và độ trễ khi truyền video trực tiếp.", "ready"),
      q(12, "Giải thích vì sao TCP dùng bắt tay ba bước.", "ready", { origin: "generated", answerSource: "ai" }),
      q(8, "So sánh Go-Back-N và Selective Repeat.", "ready", { practiced: true, mastered: true }),
      q(9, "So sánh UDP và TCP khi truyền video.", "waiting", { sectionLabel: "3.4" }),
    ],
  },
  {
    id: "g2",
    name: "Tính toán thông lượng",
    suggested: true,
    mastery: { score: 1, attempts: 2 },
    timing: { kind: "unmeasured" },
    questions: [
      q(3, "Tính thông lượng hiệu dụng của giao thức dừng-và-chờ.", "ready", { practiced: true }),
      q(5, "Tính thời gian truyền một tệp 10 MB qua liên kết 100 Mbps.", "waiting", { sectionLabel: "4.1" }),
    ],
  },
  {
    id: "g3",
    name: "Định nghĩa ngắn",
    suggested: false,
    mastery: { score: 6.5, attempts: 8 },
    timing: { kind: "near", refMinutes: 2 },
    questions: [q(1, "Định nghĩa cửa sổ nhận (rwnd).", "ready", { practiced: true }), q(2, "Định nghĩa MSS.", "ready")],
  },
];

export const UNLINKED: PracticeQuestion[] = [q(7, "Mô tả cơ chế phát hiện tắc nghẽn của TCP Reno.", "unlinked")];

export const WAITING_ONLY: PracticeGroup[] = GROUPS.map((g) => ({
  ...g,
  questions: g.questions.filter((x) => x.status === "waiting").map((x) => ({ ...x, practiced: false })),
})).filter((g) => g.questions.length > 0);

export const CANDIDATES: Candidate[] = [
  { id: "c1", text: "Vì sao TCP cần số thứ tự cho từng byte chứ không chỉ từng gói?", kind: "So sánh hai giao thức", cardLabel: "Thẻ: Số thứ tự TCP" },
  { id: "c2", text: "Nêu hai trường hợp UDP phù hợp hơn TCP và giải thích.", kind: "So sánh hai giao thức", cardLabel: "Thẻ: Khi nào dùng UDP" },
  { id: "c3", text: "Cửa sổ nhận ảnh hưởng thế nào đến tốc độ gửi?", kind: "So sánh hai giao thức", cardLabel: "Thẻ: rwnd và tốc độ gửi" },
];

export const SECTIONS: StudiedSection[] = [
  { id: "s1", label: "3.1 Dịch vụ tầng giao vận", studied: true },
  { id: "s2", label: "3.2 TCP flow control", studied: true },
  { id: "s3", label: "3.3 Kiểm soát tắc nghẽn", studied: false },
  { id: "s4", label: "3.4 UDP", studied: false },
];

export const IMPORTED_FILE = "de-cuong-on-tap.pdf";
export const IMPORTED_NOTE = "Đã tách 24 câu. App gợi ý 4 dạng câu; bạn sửa được bằng thanh lệnh.";

export const RESULT: Result = {
  grade_id: "0b8f1d2e-0000-4000-8000-0000000000e1",
  overall: "partial",
  understanding: 2,
  missing: ["Nêu vai trò của số thứ tự trong bắt tay ba bước."],
  units: [
    { unit_id: "0b8f1d2e-0000-4000-8000-0000000000c1", title: "Độ tin cậy của TCP", verdict: "correct" },
    { unit_id: "0b8f1d2e-0000-4000-8000-0000000000c2", title: "Kiểm soát luồng", verdict: "partial" },
    { unit_id: "0b8f1d2e-0000-4000-8000-0000000000c3", title: "Ảnh hưởng tới video trực tiếp", verdict: "incorrect" },
  ],
  reference_answer: "TCP đảm bảo thứ tự và độ tin cậy nhưng thêm thời gian chờ; UDP nhanh hơn, hợp với video trực tiếp.",
  sources: [],
  practice: true,
};

export const RESULT_EXTRAS = {
  timing: { seconds: 130, refMinutes: 3 },
  differsFromCard: { label: "TCP flow control", href: "/subjects/0b8f1d2e-0000-4000-8000-000000000001/documents" },
  answerSource: "ai" as const,
};
