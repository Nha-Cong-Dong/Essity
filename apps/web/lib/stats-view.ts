import type { components } from "@/lib/core-client";

import type { GridCell } from "@/lib/stats";

// T9.5 (US-10 AC1, AC4): GET /v1/stats (T9.4b) -> what the T9.5a screen draws. Pure, no server
// imports, so the preview and the tests share it with the live page.

export type TypeCounts = { type: string; ready: number; practiced: number; mastered: number };

export type ViewSubject = {
  id: string;
  name: string;
  examOn: string | null;
  /** Days to the exam (negative once over); null without an exam. */
  daysLeft: number | null;
  syllabus: { studied: number; leaves: number; pagesDone: number; pages: number };
  /** null: the subject has no question bank yet. */
  bank: TypeCounts[] | null;
  /** Share of cards with recall today >= 90%, 0..1; null without cards. */
  retention: number | null;
  /** The API does not send it yet (AC10): 0 hides the line. */
  skippedCards: number;
};

export type Totals = {
  unitsLearned: number;
  unitsTotal: number;
  sessions: number;
  cardsSaved: number;
  cardsReviewed: number;
  practiceDone: number;
};

export const NO_TOTALS: Totals = {
  unitsLearned: 0,
  unitsTotal: 0,
  sessions: 0,
  cardsSaved: 0,
  cardsReviewed: 0,
  practiceDone: 0,
};

export type StatsView = { today: string; subjects: ViewSubject[]; cells: GridCell[]; totals?: Totals };

type StatsOut = components["schemas"]["StatsOut"];

const clampLevel = (n: number): GridCell["level"] =>
  Math.min(Math.max(Math.trunc(n) || 0, 0), 4) as GridCell["level"];

export function toStatsData(out: StatsOut): StatsView {
  return {
    today: out.today,
    totals: {
      unitsLearned: out.totals.units_learned,
      unitsTotal: out.totals.units_total,
      sessions: out.totals.sessions,
      cardsSaved: out.totals.cards_saved,
      cardsReviewed: out.totals.cards_reviewed,
      practiceDone: out.totals.practice_done,
    },
    subjects: out.subjects.map((s) => {
      const page = s.syllabus.by_unit.find((u) => u.unit === "page");
      return {
        id: s.id,
        name: s.name,
        examOn: s.exam_date,
        daysLeft: s.days_left,
        syllabus: {
          studied: s.syllabus.studied_leaves,
          leaves: s.syllabus.leaves,
          pagesDone: page ? Math.round(page.studied) : 0,
          pages: page ? Math.round(page.total) : 0,
        },
        bank:
          s.bank.length === 0
            ? null
            : s.bank.map((t) => ({
                type: t.question_type,
                ready: t.ready,
                practiced: t.practiced,
                mastered: t.mastered,
              })),
        retention: s.retention,
        skippedCards: 0,
      };
    }),
    cells: out.grid.map((c) => ({
      day: c.day,
      column: c.column,
      row: c.row,
      level: clampLevel(c.level),
      future: c.future,
      examDay: c.exam_day,
      subjects: c.subjects.map((x) => x.id),
      sections: c.sections.map((x) => x.name),
      cardsSaved: c.cards_saved,
      questionsAnswered: c.questions_answered,
    })),
  };
}
