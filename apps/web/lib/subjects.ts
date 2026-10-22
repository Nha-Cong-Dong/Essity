import "server-only";

import { cookies } from "next/headers";

import { type components, coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T1.20: the user's subjects, read on the server for /subjects and /subjects/[id]/upload.

export type Subject = components["schemas"]["SubjectOut"];

export { isSubjectId } from "@/lib/subject-id";

/** Every subject of the signed-in user, by exam date. Throws when core-api cannot answer. */
export async function listSubjects(): Promise<Subject[]> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).GET("/v1/subjects");
  if (!data) throw new Error(`core-api answered /v1/subjects with ${response.status}`);
  return data;
}

/**
 * One subject of the user's, or null: an id that is not a UUID, someone else's subject and one
 * that does not exist all look the same (plan K5). There is no GET /v1/subjects/{id} yet (T4.9).
 */
export async function findSubject(id: string): Promise<Subject | null> {
  if (!isSubjectId(id)) return null;
  const subjects = await listSubjects();
  return subjects.find((subject) => subject.id.toLowerCase() === id.toLowerCase()) ?? null;
}
