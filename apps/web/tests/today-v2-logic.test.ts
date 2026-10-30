// T7.13a (US-03, US-15 AC5, DESIGN §6.2): the pure rules of Hôm nay v2: pace line, primary action.
import { describe, expect, it } from "vitest";

import { BANNED_WORDS, hasBannedWord, nextDueLabel, paceLine, primaryAction, type TodayV2 } from "@/lib/today-v2";

describe("paceLine", () => {
  it("US-15 AC5: full line", () => {
    expect(paceLine({ sections_left: 12, pages_left: 86, days_left: 20 })).toBe("còn 12 mục (86 trang), 20 ngày");
  });
  it("US-15 AC5: one day, exam today, no date, no pages", () => {
    expect(paceLine({ sections_left: 3, pages_left: 20, days_left: 1 })).toBe("còn 3 mục (20 trang), 1 ngày");
    expect(paceLine({ sections_left: 3, pages_left: 20, days_left: 0 })).toBe("còn 3 mục (20 trang), thi hôm nay");
    expect(paceLine({ sections_left: 3, pages_left: 20, days_left: null })).toBe("còn 3 mục (20 trang)");
    expect(paceLine({ sections_left: 3, pages_left: null, days_left: 5 })).toBe("còn 3 mục, 5 ngày");
  });
  // US-15 AC5. Red when: a pace line uses a banned word.
  it("never uses a banned word", () => {
    for (const days of [null, 0, 1, 40]) {
      expect(hasBannedWord(paceLine({ sections_left: 1, pages_left: 9, days_left: days }))).toBe(false);
    }
  });
});

describe("hasBannedWord", () => {
  it("US-15 AC5: catches whole words only", () => {
    for (const word of BANNED_WORDS) expect(hasBannedWord(`Bạn ${word} học`)).toBe(true);
    expect(hasBannedWord("Cần thơ")).toBe(true);
    expect(hasBannedWord("Hôm nay nên học")).toBe(false);
    expect(hasBannedWord("phải")).toBe(true);
    expect(hasBannedWord("phảivà")).toBe(false);
  });
});

describe("nextDueLabel", () => {
  it("US-03 AC1: builds the sentence from the real date", () => {
    expect(nextDueLabel("2026-10-22")).toBe("Lần tới đến hạn: thứ Năm, 22/10");
  });
});

const EMPTY: TodayV2 = {
  learning_day: "2026-10-30",
  subject_count: 2,
  unfinished: [],
  review: { state: "none", next_due: null },
  learn: { items: [], empty_reason: "exams_over" },
  practice: null,
};

describe("primaryAction", () => {
  const due: Extract<TodayV2["review"], { state: "due" }> = {
    state: "due",
    count: 5,
    minutes: 8,
    subjects: ["A"],
    in_progress: false,
  };
  const item = {
    subject: { id: "x", name: "A" },
    state: "next",
    section: { label: "3.2", title: "T", pages: "tr. 1–2" },
    reason: "r",
    pace: { sections_left: 1, pages_left: null, days_left: null },
  } as const;
  const rows = [{ subject_id: "x", name: "A", ready: 5, kinds: 2 }];

  it("US-03 AC1, US-15 AC1: follows the priority of DESIGN §6.2", () => {
    const resume = { kind: "review", session_id: "s", position: 7, total: 14 } as const;
    expect(primaryAction({ ...EMPTY, unfinished: [resume], review: due })).toBe("unfinished");
    expect(primaryAction({ ...EMPTY, review: due })).toBe("review");
    expect(primaryAction({ ...EMPTY, learn: { items: [item], empty_reason: null } })).toBe("learn");
    expect(primaryAction({ ...EMPTY, practice: { state: "ready", rows } })).toBe("practice");
    expect(primaryAction(EMPTY)).toBeNull();
    expect(primaryAction({ ...EMPTY, subject_count: 0 })).toBe("create");
  });
  it("US-03 AC1: a review already in progress is not a second entry", () => {
    expect(primaryAction({ ...EMPTY, review: { ...due, in_progress: true } })).toBeNull();
  });
});
