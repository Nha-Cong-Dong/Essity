import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";
import type { OutlineOut } from "@/lib/syllabus/api";

// T7.5 (US-13): the outline of a subject, read on the server for /subjects/[id]/syllabus.

/** The outline of the user's subject. Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function loadOutline(subjectId: string): Promise<OutlineOut> {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/subjects/{id}/outline", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).GET("/v1/subjects/{subject_id}/outline", {
    params: { path: { subject_id: subjectId } },
  });
  if (!data) throw new CoreStatusError("/v1/subjects/{id}/outline", response.status);
  return data;
}
