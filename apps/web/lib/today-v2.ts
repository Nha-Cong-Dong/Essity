import { dayLabel } from "@/lib/today-copy";

// T7.13a (US-03, US-15, DESIGN §6.2): the shape Hôm nay v2 draws, and its pure rules. Static
// fixtures feed it now; T7.13 swaps them for the T7.11 API. Strings are copy by Claude (30/10),
// marked data-copy="tam" where drawn until the user tweaks them.

export type Pace = {
  sections_left: number;
  pages_left: number | null;
  days_left: number | null;
  /** The API's ready-made line (T7.13); the fixtures omit it and `paceLine` builds one. */
  text?: string;
};
export type NamedSubject = { id: string; name: string };

export type LearnItem =
  | {
      subject: NamedSubject;
      state: "next";
      section: { label: string; title: string; pages: string | null };
      reason: string;
      pace: Pace;
    }
  | { subject: NamedSubject; state: "no_textbook" }
  | { subject: NamedSubject; state: "finished" };

export type Unfinished =
  | { kind: "review"; session_id: string; position: number; total: number }
  | { kind: "draft"; subject: NamedSubject; drafts: number }
  | { kind: "session"; subject: NamedSubject; session_id: string; line: string }
  | { kind: "note"; text: string };

export type EmptyReason = "exams_over" | "no_textbook" | "finished";
export type PracticeRow = { subject_id: string; name: string; ready: number; kinds: number };

export type TodayV2 = {
  learning_day: string;
  subject_count: number;
  unfinished: Unfinished[];
  review:
    | { state: "due"; count: number; minutes: number; subjects: string[]; in_progress: boolean; note?: string }
    | { state: "none"; next_due: string | null };
  learn: { items: LearnItem[]; empty_reason: EmptyReason | null };
  /** null: no question bank yet (the block is hidden). */
  practice: null | { state: "none_ready" } | { state: "ready"; rows: PracticeRow[] };
};

/** "còn 12 mục (86 trang), 20 ngày": numbers only (US-15 AC5). */
export function paceLine(pace: Pace): string {
  if (pace.text) return pace.text;
  const pages = pace.pages_left === null ? "" : ` (${pace.pages_left} trang)`;
  const days = pace.days_left === null ? "" : pace.days_left === 0 ? ", thi hôm nay" : `, ${pace.days_left} ngày`;
  return `còn ${pace.sections_left} mục${pages}${days}`;
}

export function nextDueLabel(iso: string): string {
  return `Lần tới đến hạn: ${dayLabel(iso)}`;
}

/** US-15 AC5: words no suggestion text may use. */
export const BANNED_WORDS = ["phải", "cần", "kịp", "trễ"] as const;
const BANNED = new RegExp(`(^|[^\\p{L}])(${BANNED_WORDS.join("|")})($|[^\\p{L}])`, "iu");
export const hasBannedWord = (text: string): boolean => BANNED.test(text);

export type Primary = "unfinished" | "review" | "learn" | "practice" | "create" | null;

/** The one primary button of the screen (DESIGN §6.2): the others are secondary or quiet. */
export function primaryAction(today: TodayV2): Primary {
  if (today.subject_count === 0) return "create";
  if (today.unfinished.some((item) => item.kind !== "note")) return "unfinished";
  if (today.review.state === "due" && !today.review.in_progress) return "review";
  if (today.learn.items.some((item) => item.state === "next")) return "learn";
  if (today.practice?.state === "ready") return "practice";
  return null;
}

export const TODAY_V2_COPY = {
  heading: "Hôm nay",
  unfinished: "Việc dở",
  resume: "Tiếp tục",
  review: "Ôn hôm nay",
  questions: "câu",
  start: "Bắt đầu",
  inProgressHint: "Phiên ôn đang dở nằm ở mục Việc dở.",
  nothingDue: "Hôm nay không có thẻ hay câu đến hạn.",
  learn: "Học gì tiếp",
  enter: "Vào buổi học",
  noTextbook: "chưa có giáo trình chính nên chưa có đề cương.",
  uploadTextbook: "Tải giáo trình",
  finished: "Bạn đã học hết đề cương. Ôn và luyện tập là việc tiếp theo.",
  emptyReason: {
    exams_over: "Các môn đã thi xong.",
    no_textbook: "Chưa có giáo trình để gợi ý.",
    finished: "Đã học hết đề cương.",
  } satisfies Record<EmptyReason, string>,
  practice: "Luyện tập",
  openPractice: "Mở luyện tập",
  practiceNone: "Chưa có câu sẵn sàng. Câu sẽ sẵn sàng khi bạn học xong mục của nó.",
  subjects: "Môn học",
  noSubjects: "Chưa có môn nào.",
  noSubjectsHint: "Tạo môn đầu tiên bằng tên và ngày thi.",
  createSubject: "Tạo môn",
  loading: "Đang tải trang hôm nay.",
  failed: "Không tải được trang hôm nay.",
  failedHint: "Kiểm tra kết nối rồi thử lại.",
  retry: "Thử lại",
} as const;

/** "Mạng máy tính: còn 4 thẻ nháp chưa duyệt". */
export const draftLine = (name: string, drafts: number) => `${name}: còn ${drafts} thẻ nháp chưa duyệt`;
export const practiceLine = (row: PracticeRow) => `${row.name}: ${row.ready} câu sẵn sàng · ${row.kinds} dạng`;
export const reviewProgress = (position: number, total: number) => `Phiên ôn đang dở · câu ${position}/${total}`;
