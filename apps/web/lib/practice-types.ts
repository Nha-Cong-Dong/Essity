import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";
import type { PracticeType } from "@/lib/practice-client";

// T8.7 (US-16 AC4, AC8): a subject's practice types with their mastery and sensitivity lines, read
// on the server. The backend words the lines (neutral, "chưa đủ dữ liệu" under 3 answers).

/** Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function loadPracticeTypes(subjectId: string): Promise<PracticeType[]> {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/subjects/{id}/practice-types", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).GET("/v1/subjects/{subject_id}/practice-types", {
    params: { path: { subject_id: subjectId } },
  });
  if (!data) throw new CoreStatusError("/v1/subjects/{id}/practice-types", response.status);
  return data;
}
