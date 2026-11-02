import { isSubjectId } from "@/lib/subject-id";

// T7.17 (US-02 AC1): "Ghi buổi học" opens the study session (draft review after Save, resume on
// reopen). Only an old v1 `?session=` address keeps the v1 saved view, until T7.6 removes it.
export function newSessionTarget(subjectId: string, session: string | string[] | undefined): string | null {
  if (typeof session === "string" && isSubjectId(session)) return null;
  return `/subjects/${subjectId}/sessions/study`;
}
