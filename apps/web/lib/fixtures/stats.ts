import type { ActivityEvent, SubjectSpan } from "@/lib/stats";

// T9.5a: fixed data for /design-preview/stats. T9.5 replaces it with the T9.4 API
// (GET /v1/progress). Shapes mirror core_api/domain/stats.py: TypeCounts, SyllabusProgress,
// retention, days_left. Nothing here ranks or compares: no streak, no "vs last week".

export const TODAY = "2026-10-30";
export const LONG_SUBJECT = "Cơ sở lý thuyết truyền tin và mã hóa thông tin nâng cao cho hệ thống phân tán";
const LONG_TYPE = "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượng_kỳthi";

export type TypeCounts = { type: string; ready: number; practiced: number; mastered: number };

export type SubjectStats = SubjectSpan & {
  name: string;
  /** Days to the exam (negative once over); null without an exam. */
  daysLeft: number | null;
  syllabus: { studied: number; leaves: number; pagesDone: number; pages: number };
  /** null: the subject has no question bank yet. */
  bank: TypeCounts[] | null;
  /** Share of canonical cards with recall today >= 90%, 0..1; null without cards. */
  retention: number | null;
  skippedCards: number;
};

export type StatsState = "empty" | "few-days" | "full-year" | "many-subjects" | "no-exam" | "no-bank" | "loading" | "error";
export const STATS_STATE_IDS: StatsState[] = [
  "empty", "few-days", "full-year", "many-subjects", "no-exam", "no-bank", "loading", "error",
];

const NET: SubjectStats = {
  id: "0b8f1d2e-0000-4000-8000-000000000001",
  name: "Mạng máy tính",
  createdOn: "2026-09-07",
  examOn: "2026-12-15",
  daysLeft: 46,
  syllabus: { studied: 23, leaves: 52, pagesDone: 310, pages: 820 },
  bank: [
    { type: "Tính toán", ready: 6, practiced: 4, mastered: 1 },
    { type: "Giải thích", ready: 9, practiced: 3, mastered: 2 },
    { type: LONG_TYPE, ready: 3, practiced: 1, mastered: 0 },
  ],
  retention: 0.72,
  skippedCards: 4,
};
const DB: SubjectStats = {
  id: "0b8f1d2e-0000-4000-8000-000000000002",
  name: "Cơ sở dữ liệu",
  createdOn: "2026-09-21",
  examOn: "2026-12-22",
  daysLeft: 53,
  syllabus: { studied: 11, leaves: 40, pagesDone: 120, pages: 540 },
  bank: [{ type: "Viết truy vấn", ready: 5, practiced: 2, mastered: 0 }],
  retention: 0.55,
  skippedCards: 0,
};
const OS: SubjectStats = {
  id: "0b8f1d2e-0000-4000-8000-000000000003",
  name: "Hệ điều hành",
  createdOn: "2026-10-12",
  examOn: null,
  daysLeft: null,
  syllabus: { studied: 2, leaves: 30, pagesDone: 25, pages: 410 },
  bank: null,
  retention: null,
  skippedCards: 0,
};
const EXTRA = (n: number): SubjectStats => ({
  ...DB,
  id: `0b8f1d2e-0000-4000-8000-0000000001${String(n).padStart(2, "0")}`,
  name: n === 0 ? LONG_SUBJECT : `Môn học số ${n + 3}`,
  syllabus: { studied: n + 3, leaves: 36, pagesDone: 40 * (n + 1), pages: 500 },
  retention: 0.4 + n * 0.05,
});

const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const DAY = 86_400_000;

/** Deterministic pseudo-random work per day (no Math.random: the preview must not flicker). */
function eventsFor(subject: SubjectSpan, from: string, to: string, every: number, seed: number): ActivityEvent[] {
  const events: ActivityEvent[] = [];
  let i = 0;
  for (let ms = Date.parse(`${from}T00:00:00Z`); ms <= Date.parse(`${to}T00:00:00Z`); ms += DAY, i++) {
    const roll = (i * 7 + seed * 13) % every;
    if (roll !== 0 && roll !== 2) continue; // most days stay empty; that is fine, never a warning
    const cards = ((i * 5 + seed) % 9) + (roll === 0 ? 6 : 0);
    const answered = ((i * 3 + seed) % 11) + (roll === 2 ? 8 : 0);
    events.push({
      day: iso(ms),
      subjectId: subject.id,
      sections: [`Mục ${1 + (i % 7)}.${1 + (i % 4)}`],
      cardsSaved: cards,
      questionsAnswered: answered,
    });
  }
  return events;
}

export type StatsData = { today: string; subjects: SubjectStats[]; events: ActivityEvent[] };

export function statsFixture(state: StatsState): StatsData {
  switch (state) {
    case "empty":
      return { today: TODAY, subjects: [], events: [] };
    case "few-days":
      return {
        today: TODAY,
        subjects: [{ ...OS, examOn: "2026-12-15", daysLeft: 46, bank: null }],
        events: [
          { day: "2026-10-27", subjectId: OS.id, sections: ["Mục 1.1"], cardsSaved: 4, questionsAnswered: 0 },
          { day: "2026-10-29", subjectId: OS.id, sections: ["Mục 1.2", "Mục 1.3"], cardsSaved: 7, questionsAnswered: 5 },
        ],
      };
    case "no-exam":
      return { today: TODAY, subjects: [OS], events: eventsFor(OS, OS.createdOn, TODAY, 3, 1) };
    case "no-bank":
      return {
        today: TODAY,
        subjects: [{ ...NET, bank: null }],
        events: eventsFor(NET, NET.createdOn, TODAY, 4, 2),
      };
    case "many-subjects": {
      const subjects = [NET, DB, OS, EXTRA(0), EXTRA(1), EXTRA(2)];
      return {
        today: TODAY,
        subjects,
        events: subjects.flatMap((s, i) => eventsFor(s, s.createdOn, TODAY, 5, i)),
      };
    }
    case "full-year": {
      const long: SubjectStats = { ...NET, createdOn: "2026-01-12", examOn: "2026-12-15" };
      return { today: TODAY, subjects: [long, DB], events: [...eventsFor(long, "2026-01-12", TODAY, 3, 3), ...eventsFor(DB, DB.createdOn, TODAY, 4, 5)] };
    }
    default:
      return { today: TODAY, subjects: [NET, DB], events: [...eventsFor(NET, NET.createdOn, TODAY, 3, 3), ...eventsFor(DB, DB.createdOn, TODAY, 4, 5)] };
  }
}
