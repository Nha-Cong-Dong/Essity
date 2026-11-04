import type { components } from "@/lib/core-client";

import type { NextSuggestion, SuggestionState } from "@/components/subjects/subject-suggestion";
import type { EmptyReason, LearnItem, NamedSubject, Pace, TodayV2, Unfinished } from "@/lib/today-v2";

// T7.13 (US-03, US-15): the API's answers, turned into what Hôm nay v2 and the subject block draw
// (the shapes T7.13a built on fixtures). Pure; no API call here.

type Schemas = components["schemas"];
export type TodayApi = Schemas["TodayOut"];
export type SuggestionApi = Schemas["SuggestionOut"];
export type SuggestionsApi = Schemas["SuggestionsOut"];

const EMPTY: Record<string, EmptyReason> = {
  nothing_open: "exams_over",
  no_syllabus: "no_textbook",
  all_studied: "finished",
};

const paceOf = (s: SuggestionApi): Pace => ({
  sections_left: s.pace.remaining_chapters, // E2: "còn n" counts chapters
  pages_left: null,
  days_left: s.pace.days_left,
  text: s.pace.text,
});

/** "3.2 TCP flow control" -> label "3.2", title "TCP flow control"; no number: no label. */
export function splitTitle(raw: string | null): { label: string; title: string } {
  // An older build titled the fallback outline "Pages 1-10"; say "Trang 1–10" like the current one.
  const text = (raw ?? "").trim().replace(/^Pages\s+(\d+)\s*[-–]\s*(\d+)$/u, "Trang $1–$2");
  const match = /^(\d+(?:\.\d+)*)[.)]?\s+(.*)$/u.exec(text) ?? /^(\d+(?:\.\d+)*)$/u.exec(text);
  if (!match) return { label: "", title: text };
  return { label: match[1], title: match[2] ?? "" };
}

function nextOf(s: SuggestionApi): NextSuggestion {
  return { ...splitTitle(s.section_title), sectionId: s.section_id, pages: null, reason: s.reason, pace: paceOf(s) };
}

/** One suggestion, in the shape the subject block shows it. */
export function subjectState(s: SuggestionApi): SuggestionState {
  if (s.kind === "next_leaf") return { kind: "suggested", next: nextOf(s) };
  return s.kind === "free_session" ? { kind: "no_textbook" } : { kind: "finished" };
}

function learnItem(s: SuggestionApi): LearnItem {
  const subject: NamedSubject = { id: s.subject_id, name: s.subject_name };
  if (s.kind === "free_session") return { subject, state: "no_textbook" };
  if (s.kind === "review_practice") return { subject, state: "finished" };
  const { label, title } = splitTitle(s.section_title);
  // V8: the chapter the section sits in, from today's planned leaves.
  const chapter = s.units?.find((u) => u.section_id === s.section_id)?.chapter_title ?? null;
  return { subject, state: "next", section: { label, title, pages: null, id: s.section_id, chapter }, reason: s.reason, pace: paceOf(s) };
}

export function toTodayV2(today: TodayApi): TodayV2 {
  const names = new Map(today.subjects.map((s) => [s.id, s.name]));
  const subjectOf = (id: string): NamedSubject => ({ id, name: names.get(id) || "Môn học" });

  const unfinished: Unfinished[] = [];
  if (today.in_progress) unfinished.push({ kind: "review", ...today.in_progress });
  for (const item of today.unfinished) {
    unfinished.push({
      kind: "session",
      subject: subjectOf(item.subject_id),
      session_id: item.session_id,
      line: item.line,
    });
  }

  const items = today.review.items;
  const review: TodayV2["review"] =
    items.length > 0
      ? {
          state: "due",
          count: items.length,
          minutes: today.review.minutes,
          subjects: [...new Set(items.map((i) => names.get(i.subject_id) ?? ""))].filter(Boolean),
          in_progress: today.in_progress !== null,
        }
      : { state: "none", next_due: today.review.next_due_day ?? today.next_day };

  const empty = today.next_study.empty_reason;
  return {
    learning_day: today.learning_day,
    subject_count: today.subjects.length,
    unfinished,
    review,
    learn: {
      items: today.next_study.items.map(learnItem),
      empty_reason: empty === null ? null : (EMPTY[empty] ?? "no_textbook"),
    },
    // US-03 AC7: the rows /v1/today sends (ready, never attempted, by subject); none: the neutral line.
    practice:
      today.practice && today.practice.lines.length > 0
        ? {
            state: "ready",
            rows: today.practice.lines.map((l) => ({
              subject_id: l.subject_id,
              name: l.subject_name,
              ready: l.ready_questions,
              kinds: l.question_types,
            })),
          }
        : { state: "none_ready" },
  };
}

/** What the subject screen shows first, from GET /v1/suggestions (US-15 AC6, AC7). */
export function suggestionState(all: SuggestionsApi, subjectId: string, daysUntilExam: number): SuggestionState {
  if (daysUntilExam < 0) return { kind: "exam_over" };
  const mine = all.suggestions.find((s) => s.subject_id === subjectId);
  if (mine) return subjectState(mine);
  const done = all.finished.find((s) => s.subject_id === subjectId);
  if (done) return subjectState(done);
  return { kind: "not_suggested" };
}
