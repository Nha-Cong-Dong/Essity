import type { SuggestionState } from "@/components/subjects/subject-suggestion";
import { subjectState, type SuggestionApi } from "@/lib/today-adapt";

// T7.13 (US-15 AC6): the browser's side of "Gợi ý cho hôm nay". Any answer that is not a usable
// suggestion throws, so the block can say so instead of waiting on "Đang tính…".

/** Asks web's route for this subject's suggestion now. Throws when there is none to show. */
export async function fetchSubjectSuggestion(subjectId: string): Promise<SuggestionState> {
  const response = await fetch(`/api/subjects/${subjectId}/suggestion`, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`suggestion ${response.status}`);
  const body = (await response.json()) as { suggestion?: SuggestionApi } | null;
  if (!body?.suggestion || typeof body.suggestion.kind !== "string") throw new Error("suggestion shape");
  return subjectState(body.suggestion);
}
