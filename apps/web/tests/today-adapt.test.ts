// T7.13 (US-03, US-15): GET /v1/today v2 and the suggestion endpoints, as the screens draw them.
import { describe, expect, it } from "vitest";

import { subjectState, suggestionState, toTodayV2, type TodayApi } from "@/lib/today-adapt";
import { hasBannedWord } from "@/lib/today-v2";

const A = "0b8f1d2e-0000-4000-8000-000000000001";
const B = "0b8f1d2e-0000-4000-8000-000000000002";
const SID = "5f0c0000-0000-4000-8000-000000000001";

const pace = { remaining_leaves: 12, remaining_weight: 12, unit: "mục", days_left: 20, text: "còn 12 mục, 20 ngày" };
const next = (over = {}) => ({
  subject_id: A,
  subject_name: "Mạng máy tính",
  kind: "next_leaf" as const,
  section_id: SID,
  section_title: "3.2 TCP flow control" as string | null,
  partial: false,
  remaining: null,
  unit: "mục",
  reason: "Môn thi sau 20 ngày, còn 12 mục.",
  pace,
  ...over,
});

const base = (over: Partial<TodayApi> = {}): TodayApi => ({
  learning_day: "2026-11-02",
  state: "rested",
  session: null,
  in_progress: null,
  backlog: null,
  next_day: "2026-11-03",
  practice: null,
  subjects: [
    { id: A, name: "Mạng máy tính", exam_date: "2026-12-15", days_until_exam: 43 },
    { id: B, name: "Hệ điều hành", exam_date: "2026-12-20", days_until_exam: 48 },
  ],
  review: { items: [], minutes: 0, new_saved_today: false, next_due_day: "2026-11-05" },
  unfinished: [],
  next_study: { items: [], empty_reason: null, links: ["review", "practice", "subjects"] },
  ...over,
});

describe("toTodayV2", () => {
  // Red when: the screen invents a review count or hides the next due day.
  it("US-03 AC1: nothing due keeps the next due day", () => {
    expect(toTodayV2(base()).review).toEqual({ state: "none", next_due: "2026-11-05" });
  });

  // Red when: the pink tile counts something other than the API's questions, or repeats a subject.
  it("US-03 AC1: due items give the count, minutes and each subject once", () => {
    const item = (subject_id: string) => ({ question_id: SID, subject_id, why: "x", reason: { kind: "due" } as never });
    const out = toTodayV2(
      base({
        review: { items: [item(A), item(A), item(B)], minutes: 5, new_saved_today: false, next_due_day: null },
      }),
    );
    expect(out.review).toMatchObject({
      state: "due",
      count: 3,
      minutes: 5,
      subjects: ["Mạng máy tính", "Hệ điều hành"],
      in_progress: false,
    });
  });

  // Red when: an open review session is offered as a fresh start instead of under Việc dở.
  it("US-03: an open review session is Việc dở", () => {
    const out = toTodayV2(base({ in_progress: { session_id: SID, position: 7, total: 14 } }));
    expect(out.unfinished[0]).toEqual({ kind: "review", session_id: SID, position: 7, total: 14 });
  });

  // Red when: an unfinished study session loses its subject or line.
  it("US-03: an unfinished study session links to its subject", () => {
    const out = toTodayV2(base({ unfinished: [{ session_id: SID, subject_id: B, line: "Buổi học đang dở" }] }));
    expect(out.unfinished).toEqual([
      { kind: "session", subject: { id: B, name: "Hệ điều hành" }, session_id: SID, line: "Buổi học đang dở" },
    ]);
  });

  // Red when: a session whose subject is not in today's list gets an empty name (a blank button label).
  it("an unfinished session of an unlisted subject gets a neutral name", () => {
    const out = toTodayV2(base({ unfinished: [{ session_id: SID, subject_id: "other", line: "x" }] }));
    expect(out.unfinished[0]).toMatchObject({ subject: { id: "other", name: "Môn học" } });
  });

  // Red when: a suggestion is shown without its section, reason or the API's pace line.
  it("US-15 AC1: next_leaf becomes a section with the reason and the API pace", () => {
    const out = toTodayV2(base({ next_study: { items: [next()], empty_reason: null, links: [] } }));
    expect(out.learn.items[0]).toMatchObject({
      state: "next",
      subject: { id: A, name: "Mạng máy tính" },
      section: { label: "3.2", title: "TCP flow control", pages: null },
      reason: "Môn thi sau 20 ngày, còn 12 mục.",
      pace: { text: "còn 12 mục, 20 ngày" },
    });
  });

  // Red when: free_session / review_practice are drawn as a section to study.
  it("US-15 AC7: free_session is no textbook, review_practice is finished", () => {
    const out = toTodayV2(
      base({
        next_study: {
          items: [
            next({ kind: "free_session", section_title: null }),
            next({ kind: "review_practice", section_title: null, subject_id: B, subject_name: "Hệ điều hành" }),
          ],
          empty_reason: null,
          links: [],
        },
      }),
    );
    expect(out.learn.items.map((i) => i.state)).toEqual(["no_textbook", "finished"]);
  });

  // Red when: the AC11 empty reasons are not told apart.
  it.each([
    ["nothing_open", "exams_over"],
    ["no_syllabus", "no_textbook"],
    ["all_studied", "finished"],
  ])("US-15 AC11: empty reason %s", (reason, expected) => {
    const out = toTodayV2(base({ next_study: { items: [], empty_reason: reason, links: [] } }));
    expect(out.learn.empty_reason).toBe(expected);
  });

  // Red when: no subjects is not the create-subject state.
  it("US-03: no subjects", () => {
    expect(toTodayV2(base({ state: "no_subjects", subjects: [] })).subject_count).toBe(0);
  });

  // Red when: practice invents rows before M8 sends any, or the block is blank.
  it("US-03 AC7: practice is the neutral empty state while the API sends none", () => {
    expect(toTodayV2(base()).practice).toEqual({ state: "none_ready" });
  });

  // Red when: the adapter adds a pressure word (US-15 AC5).
  it("US-15 AC5: no banned word in what the adapter adds", () => {
    expect(hasBannedWord(JSON.stringify(toTodayV2(base())))).toBe(false);
  });
});

describe("suggestionState (subject screen)", () => {
  const list = (over = {}) => ({ today: "2026-11-02", suggestions: [], finished: [], empty: null, ...over });

  // Red when: a subject in today's list shows the button instead of its section.
  it("US-15 AC6: in today's suggestions shows the section", () => {
    expect(suggestionState(list({ suggestions: [next()] }), A, 43)).toMatchObject({
      kind: "suggested",
      next: { label: "3.2", title: "TCP flow control" },
    });
  });

  // Red when: a subject missing from today's list is not offered the button.
  it("US-15 AC6: not in today's list is the button", () => {
    expect(suggestionState(list({ suggestions: [next({ subject_id: B })] }), A, 43)).toEqual({ kind: "not_suggested" });
  });

  // Red when: a finished or textbook-less subject gets the button.
  it("US-15 AC7: finished and no textbook", () => {
    expect(suggestionState(list({ finished: [next({ kind: "review_practice" })] }), A, 43)).toEqual({ kind: "finished" });
    expect(suggestionState(list({ finished: [next({ kind: "free_session" })] }), A, 43)).toEqual({ kind: "no_textbook" });
  });

  // Red when: a subject whose exam passed gets a suggestion.
  it("US-15 AC7: exam passed", () => {
    expect(suggestionState(list({ suggestions: [next()] }), A, -1)).toEqual({ kind: "exam_over" });
  });
});

describe("subjectState (the button's answer)", () => {
  // Red when: the button's answer is shown in another shape than the one already there.
  it("each kind maps to the same states", () => {
    expect(subjectState(next())).toMatchObject({ kind: "suggested" });
    expect(subjectState(next({ kind: "review_practice" }))).toEqual({ kind: "finished" });
    expect(subjectState(next({ kind: "free_session" }))).toEqual({ kind: "no_textbook" });
  });

  // Red when: a title without a number loses its text.
  it("a title with no number keeps the whole title and no label", () => {
    expect(subjectState(next({ section_title: "Giới thiệu" }))).toMatchObject({
      next: { label: "", title: "Giới thiệu" },
    });
  });
});
