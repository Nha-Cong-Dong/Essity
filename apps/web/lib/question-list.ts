import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";
import type { QuestionListOut } from "@/lib/question-list-types";

// T8.2 (US-14 AC6): a subject's bank questions with their readiness, read on the server.

/** The list for the user's subject. Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function loadQuestionList(subjectId: string): Promise<QuestionListOut> {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/subjects/{id}/questions", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).GET("/v1/subjects/{subject_id}/questions", {
    params: { path: { subject_id: subjectId } },
  });
  if (!data) throw new CoreStatusError("/v1/subjects/{id}/questions", response.status);
  return data;
}
