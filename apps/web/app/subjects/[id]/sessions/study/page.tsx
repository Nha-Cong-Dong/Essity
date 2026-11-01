import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { coreClient } from "@/lib/core-client";
import { requireVerifiedSession, SESSION_COOKIE } from "@/lib/session";

export const metadata: Metadata = { title: "Buổi học · Essity" };

// T7.12 (US-02 AC13): a new study session of the subject. Opens an empty draft session in core-api
// and goes to its page; the address of that page is what "resume" uses. Reached by a link, never
// prefetched (the page is dynamic), so one open makes one empty session at most.
async function Start({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).POST("/v1/subjects/{subject_id}/submission-drafts", {
    params: { path: { subject_id: subject.id } },
  });
  if (response.status === 401) redirect("/login");
  if (!data) throw new Error(`core-api answered submission-drafts with ${response.status}`);
  redirect(`/subjects/${subject.id}/sessions/${data.session_id}`);
}

export default function NewStudySession({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Start params={params} />
    </Suspense>
  );
}
