"use client";

import { SubjectSuggestion, type SuggestionState } from "@/components/subjects/subject-suggestion";
import { fetchSubjectSuggestion } from "@/lib/suggestion-client";

// T7.13 (US-15 AC6, AC7): the subject screen's block with the real endpoint behind its button.
export function SubjectScreenBlock({
  subjectId,
  subjectName,
  state,
}: {
  subjectId: string;
  subjectName: string;
  state: SuggestionState;
}) {
  return (
    <SubjectSuggestion
      subjectId={subjectId}
      subjectName={subjectName}
      state={state}
      resolve={() => fetchSubjectSuggestion(subjectId)}
      practiceLink={false}
    />
  );
}
