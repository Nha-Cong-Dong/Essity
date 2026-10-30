import type { SuggestionState } from "@/components/subjects/subject-suggestion";
import type { LearnItem, TodayV2 } from "@/lib/today-v2";

// T7.13a: fixed data for /design-preview/today and /design-preview/subject. T7.13 replaces these
// with the T7.11 API. The busiest state has a long unbroken name (CSDL_nâng_cao_…).

export const LONG_WORD = "Kiếntrúcmáytínhvàhệđiềuhànhnângcaohọckỳhainămhaingànhaimươisáu_kếtthúc";
const MMT = { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" };
const LONG = { id: "0b8f1d2e-0000-4000-8000-000000000002", name: LONG_WORD };
const HDH = { id: "0b8f1d2e-0000-4000-8000-000000000003", name: "Hệ điều hành" };

const NEXT_MMT: LearnItem = {
  subject: MMT,
  state: "next",
  section: { label: "3.2", title: "TCP flow control", pages: "tr. 52–58" },
  reason: "Môn có kỳ thi gần nhất, mục này là mục chưa học đầu tiên.",
  pace: { sections_left: 12, pages_left: 86, days_left: 20 },
};
const NEXT_LONG: LearnItem = {
  subject: LONG,
  state: "next",
  section: { label: "1.4", title: "Quản lý bộ nhớ ảo và phân trang theo yêu cầu", pages: "tr. 20–31" },
  reason: "Môn lâu chưa học nhất trong các môn cùng mức.",
  pace: { sections_left: 30, pages_left: 240, days_left: 82 },
};

const BASE: TodayV2 = {
  learning_day: "2026-10-30",
  subject_count: 3,
  unfinished: [],
  review: { state: "none", next_due: "2026-11-02" },
  learn: { items: [], empty_reason: "exams_over" },
  practice: null,
};

const BUSY: TodayV2 = {
  ...BASE,
  unfinished: [
    { kind: "review", session_id: "5f0c0000-0000-4000-8000-000000000001", position: 7, total: 14 },
    { kind: "draft", subject: LONG, drafts: 4 },
    { kind: "note", text: "Bài nộp của buổi học tối qua đang được đọc." },
  ],
  review: { state: "due", count: 14, minutes: 21, subjects: [MMT.name, LONG_WORD], in_progress: true },
  learn: { items: [NEXT_MMT, NEXT_LONG], empty_reason: null },
  practice: {
    state: "ready",
    rows: [
      { subject_id: MMT.id, name: MMT.name, ready: 5, kinds: 2 },
      { subject_id: LONG.id, name: LONG_WORD, ready: 12, kinds: 3 },
    ],
  },
};

export const TODAY_STATES: Record<string, TodayV2> = {
  busy: BUSY,
  // No unfinished work: the pink Ôn tile carries the one primary.
  review: {
    ...BUSY,
    unfinished: [],
    review: { state: "due", count: 14, minutes: 21, subjects: [MMT.name, LONG_WORD], in_progress: false },
  },
  // Nothing due: a suggestion carries the primary; a subject without a textbook has its own block.
  learn: {
    ...BASE,
    learn: { items: [NEXT_MMT, { subject: HDH, state: "no_textbook" }], empty_reason: null },
    practice: { state: "none_ready" },
  },
  finished: { ...BASE, learn: { items: [{ subject: MMT, state: "finished" }], empty_reason: null } },
  "none-exams": BASE,
  "none-textbook": { ...BASE, learn: { items: [], empty_reason: "no_textbook" } },
  "no-subjects": { ...BASE, subject_count: 0 },
};

export const SUBJECT_NEXT = {
  label: "3.2",
  title: "TCP flow control",
  pages: "tr. 52–58",
  reason: "Môn có kỳ thi gần nhất, mục này là mục chưa học đầu tiên.",
  pace: { sections_left: 12, pages_left: 86, days_left: 20 },
};

export const SUBJECT_STATES: Record<string, SuggestionState> = {
  suggested: { kind: "suggested", next: SUBJECT_NEXT },
  "not-suggested": { kind: "not_suggested" },
  finished: { kind: "finished" },
  "exam-over": { kind: "exam_over" },
  "no-textbook": { kind: "no_textbook" },
  reading: { kind: "reading" },
};

export const SUBJECT_FIXTURE = { id: MMT.id, name: MMT.name, exam_date: "15/12/2026", days: 46 };
export const SUBJECT_LONG = { id: LONG.id, name: LONG_WORD, exam_date: "15/01/2027", days: 77 };
