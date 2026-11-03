import { isSubjectId } from "@/lib/subject-id";

// T7.17 (US-02 AC1): "Ghi buổi học" opens the study session (draft review after Save, resume on
// reopen). The old v1 `?session=` address keeps the v1 saved view until T7.6 removes it, and
// `?v1=1` is where the study start sends the learner when core-api has submissions off (its
// submission-drafts answers 404): the v1 page must not bounce back, or there is a loop.
export function newSessionTarget(
  subjectId: string,
  session: string | string[] | undefined,
  v1?: string | string[],
  section?: string | string[],
): string | null {
  if (v1 === "1") return null;
  if (typeof session === "string" && isSubjectId(session)) return null;
  return studyHref(subjectId, sectionParam(section));
}

/** T7.19 F2: the one id a `?section=` query holds (the section a suggestion opened the session for). */
export const sectionParam = (value: string | string[] | undefined): string | null =>
  typeof value === "string" && isSubjectId(value) ? value : null;

/** The study session's start; a suggestion's section rides along, "Học tự do" has none. */
export const studyHref = (subjectId: string, sectionId?: string | null): string =>
  `/subjects/${subjectId}/sessions/study${sectionId && isSubjectId(sectionId) ? `?section=${sectionId}` : ""}`;

export const v1Fallback = (subjectId: string): string => `/subjects/${subjectId}/sessions/new?v1=1`;
