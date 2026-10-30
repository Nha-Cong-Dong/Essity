"use client";

import { SubjectSuggestion, type SuggestionState } from "@/components/subjects/subject-suggestion";
import { SUBJECT_NEXT } from "@/lib/fixtures/today-v2";

// A function cannot cross from a server page to a client component, so the fixture's "answer" lives here.
export function SubjectBlock({ subjectId, subjectName, state }: { subjectId: string; subjectName: string; state: SuggestionState }) {
  return <SubjectSuggestion subjectId={subjectId} subjectName={subjectName} state={state} resolve={async () => SUBJECT_NEXT} />;
}
