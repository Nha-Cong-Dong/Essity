import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { coreClient } from "@/lib/core-client";
import { requireVerifiedSession, SESSION_COOKIE } from "@/lib/session";
import { v1Fallback } from "@/lib/session-study/entry";

// T7.12 (US-02 AC13): a new study session of the subject. Opens an empty draft session in core-api
// and goes to its page (T7.18: core-api answers the open draft again when there is one, so
// reopening continues it, US-02 AC1). Reached by a link, never
// prefetched (the page is dynamic), so one open makes one empty session at most.
export async function StartStudy({ params, section }: { params: Promise<{ id: string }>; section?: string | null }): Promise<ReactNode> {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).POST("/v1/subjects/{subject_id}/submission-drafts", {
    params: { path: { subject_id: subject.id } },
  });
  if (response.status === 401) redirect("/login");
  // Submissions off in core-api (404): the v1 flow still works, so go there (T7.17).
  if (response.status === 404) redirect(v1Fallback(subject.id));
  if (!data) throw new Error(`core-api answered submission-drafts with ${response.status}`);
  // T7.19 F2: the suggestion's section follows the learner into the session.
  redirect(`/subjects/${subject.id}/sessions/${data.session_id}${section ? `?section=${section}` : ""}`);
}
