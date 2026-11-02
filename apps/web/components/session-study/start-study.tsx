import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { coreClient } from "@/lib/core-client";
import { requireVerifiedSession, SESSION_COOKIE } from "@/lib/session";
import { v1Fallback } from "@/lib/session-study/entry";

// T7.12 (US-02 AC13): a new study session of the subject. Opens an empty draft session in core-api
// and goes to its page; the address of that page is what "resume" uses. Reached by a link, never
// prefetched (the page is dynamic), so one open makes one empty session at most.
export async function StartStudy({ params }: { params: Promise<{ id: string }> }): Promise<ReactNode> {
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
  redirect(`/subjects/${subject.id}/sessions/${data.session_id}`);
}
