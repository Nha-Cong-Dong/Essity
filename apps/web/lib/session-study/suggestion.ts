import type { Suggestion } from "@/lib/fixtures/session-study";
import { splitTitle, type SuggestionApi, type SuggestionsApi } from "@/lib/today-adapt";

// T7.19 F2: a session opened from a suggestion ("Vào buổi học", ?section=) shows that section. It
// must still be today's suggestion for the subject; anything else (no section, a stale link,
// another subject's) is the free session, never a section the learner was not given.
export function sessionSuggestion(all: SuggestionsApi, subjectId: string, sectionId: string | null): Suggestion | null {
  if (sectionId === null) return null;
  const mine = all.suggestions.find((s) => s.subject_id === subjectId && s.kind === "next_leaf" && s.section_id === sectionId);
  if (!mine) return null;
  const { label, title } = splitTitle(mine.section_title);
  return {
    kind: "section",
    text: `Nội dung học tập: ${label ? `${label} ` : ""}${title}`.replace(/\.pdf\b/gi, "").trim(),
    reason: mine.reason,
    pace: mine.pace.text,
  };
}

/** SESSION-END: free study ("Học tiếp", or no schedule today). Still the next section by the
 * outline, and finishing it counts toward progress, so it is a section session, not an unlinked one. */
export function freeSuggestion(s: SuggestionApi): { suggestion: Suggestion; sectionId: string } | null {
  if (!s.free_section_id) return null;
  const { label, title } = splitTitle(s.free_section_title);
  return {
    sectionId: s.free_section_id,
    suggestion: {
      kind: "section",
      text: `Nội dung học tập: ${label ? `${label} ` : ""}${title}`.replace(/\.pdf\b/gi, "").trim(),
      reason: s.reason,
      pace: s.pace.text,
    },
  };
}
