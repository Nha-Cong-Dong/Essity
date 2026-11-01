import { describe, expect, it } from "vitest";

import type { components } from "@essity/api-client";

import { toStatsData } from "@/lib/stats-view";

// T9.5 (US-10 AC1, AC4, AC6): GET /v1/stats -> the shapes the T9.5a screen draws.
type Out = components["schemas"]["StatsOut"];

const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const OUT: Out = {
  today: "2026-10-30",
  subjects: [
    {
      id: SUBJECT,
      name: "Mạng máy tính",
      exam_date: "2026-12-15",
      days_left: 46,
      syllabus: {
        leaves: 52,
        studied_leaves: 23,
        percent: 44,
        by_unit: [
          { unit: "slide", studied: 3, total: 10 },
          { unit: "page", studied: 310.4, total: 820 },
        ],
      },
      bank: [{ question_type: "Tính toán", ready: 6, practiced: 4, mastered: 1 }],
      retention: 0.72,
    },
  ],
  grid: [
    {
      day: "2026-10-29",
      column: 0,
      row: 3,
      level: 2,
      future: false,
      exam_day: false,
      subjects: [{ id: SUBJECT, name: "Mạng máy tính" }],
      sections: [{ id: "s1", name: "Mục 1.1" }],
      cards_saved: 7,
      questions_answered: 5,
    },
  ],
};

describe("toStatsData", () => {
  it("US-10 AC1: maps a subject, taking pages from the page unit only", () => {
    const [s] = toStatsData(OUT).subjects;
    expect(s).toMatchObject({ id: SUBJECT, name: "Mạng máy tính", examOn: "2026-12-15", daysLeft: 46, retention: 0.72 });
    expect(s.syllabus).toEqual({ studied: 23, leaves: 52, pagesDone: 310, pages: 820 });
    expect(s.bank).toEqual([{ type: "Tính toán", ready: 6, practiced: 4, mastered: 1 }]);
  });

  it("US-10 AC1: no bank rows means no bank; no page unit means zero pages", () => {
    const bare: Out = {
      ...OUT,
      subjects: [{ ...OUT.subjects[0], bank: [], syllabus: { leaves: 0, studied_leaves: 0, percent: null, by_unit: [] } }],
    };
    const [s] = toStatsData(bare).subjects;
    expect(s.bank).toBeNull();
    expect(s.syllabus.pages).toBe(0);
  });

  it("US-10 AC4: maps a grid cell, subject ids and section names", () => {
    const [cell] = toStatsData(OUT).cells;
    expect(cell).toEqual({
      day: "2026-10-29", column: 0, row: 3, level: 2, future: false, examDay: false,
      subjects: [SUBJECT], sections: ["Mục 1.1"], cardsSaved: 7, questionsAnswered: 5,
    });
  });

  it("US-10 AC4: a level outside 0..4 is clamped, never trusted", () => {
    const wild: Out = { ...OUT, grid: [{ ...OUT.grid[0], level: 9 }] };
    expect(toStatsData(wild).cells[0].level).toBe(4);
  });
});
