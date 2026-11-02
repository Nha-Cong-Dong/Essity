import { isSubjectId } from "@/lib/subject-id";

// T7.17 (US-02 AC1): "Ghi buổi học" opens the study session (draft review after Save, resume on
// reopen). The old v1 `?session=` address keeps the v1 saved view until T7.6 removes it, and
// `?v1=1` is where the study start sends the learner when core-api has submissions off (its
// submission-drafts answers 404): the v1 page must not bounce back, or there is a loop.
export function newSessionTarget(
  subjectId: string,
  session: string | string[] | undefined,
  v1?: string | string[],
): string | null {
  if (v1 === "1") return null;
  if (typeof session === "string" && isSubjectId(session)) return null;
  return `/subjects/${subjectId}/sessions/study`;
}

export const v1Fallback = (subjectId: string): string => `/subjects/${subjectId}/sessions/new?v1=1`;
