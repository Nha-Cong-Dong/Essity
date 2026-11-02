import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { toGraphData } from "@/lib/graph-live";
import type { GraphData } from "@/lib/graph";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";

// T9.10 (US-19 AC3): the graph of a subject, read on the server for /subjects/[id]/graph. A section
// that is not the subject's is dropped (the whole subject is shown), not an error page.

/** Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function loadGraph(subjectId: string, sectionId: string | null): Promise<GraphData> {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/subjects/{id}/graph", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const core = coreClient({ token });
  const query = sectionId !== null && isSubjectId(sectionId) ? { section_id: sectionId } : undefined;
  let { data, response } = await core.GET("/v1/subjects/{subject_id}/graph", {
    params: { path: { subject_id: subjectId }, query },
  });
  if (!data && query !== undefined && response.status === 404) {
    ({ data, response } = await core.GET("/v1/subjects/{subject_id}/graph", {
      params: { path: { subject_id: subjectId } },
    }));
  }
  if (!data) throw new CoreStatusError("/v1/subjects/{id}/graph", response.status);
  return toGraphData(data);
}
