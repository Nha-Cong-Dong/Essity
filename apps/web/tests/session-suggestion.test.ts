// T7.19 F2: the session opened from a suggestion shows that section; any other session is free.
import { describe, expect, it } from "vitest";

import { sessionSuggestion } from "@/lib/session-study/suggestion";
import type { SuggestionsApi } from "@/lib/today-adapt";

const A = "0b8f1d2e-0000-4000-8000-000000000001";
const SEC = "5f0c0000-0000-4000-8000-000000000001";
const pace = { remaining_chapters: 12, remaining_leaves: 12, remaining_weight: 12, unit: "mục", days_left: 20, text: "còn 12 mục, 20 ngày" };
const one = (over = {}) => ({
  subject_id: A, subject_name: "Mạng", kind: "next_leaf" as const, section_id: SEC,
  section_title: "3.2 TCP flow control", partial: false, remaining: null, unit: "mục",
  reason: "Mục chưa học đầu tiên.", pace, units: [] as { section_id: string; title: string; chapter_title: string | null }[], nothing_today: false, remaining_chapters: 12, ...over,
});
const all = (suggestions: ReturnType<typeof one>[]): SuggestionsApi => ({ today: "2026-11-03", suggestions, finished: [], empty: null });

describe("sessionSuggestion", () => {
  // Red when: "Vào buổi học" from a suggestion still shows the free session.
  it("is the suggested section when the section is today's suggestion for the subject", () => {
    expect(sessionSuggestion(all([one()]), A, SEC)).toEqual({
      kind: "section",
      text: "Nội dung học tập: 3.2 TCP flow control",
      reason: "Mục chưa học đầu tiên.",
      pace: "còn 12 mục, 20 ngày",
    });
  });

  // Red when: a section that is not today's suggestion (a stale link, another subject's) is shown as one.
  it("is null for no section, another section, another subject or no suggestions", () => {
    expect(sessionSuggestion(all([one()]), A, null)).toBeNull();
    expect(sessionSuggestion(all([one()]), A, "5f0c0000-0000-4000-8000-0000000000ff")).toBeNull();
    expect(sessionSuggestion(all([one()]), "0b8f1d2e-0000-4000-8000-000000000002", SEC)).toBeNull();
    expect(sessionSuggestion(all([]), A, SEC)).toBeNull();
  });
});
