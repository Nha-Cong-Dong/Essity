import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { SessionLive } from "@/components/session-study/session-live";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { requireVerifiedSession } from "@/lib/session";
import { loadSession } from "@/lib/session-study/load";
import { CoreStatusError } from "@/lib/subjects";

export const metadata: Metadata = { title: "Buổi học · Essity" };

// T7.12 (US-02, US-02b; DESIGN.md §6.7): one session on one screen. It opens where the session
// is: a form, the reading still running, or the cards still to review (so leaving and coming back
// keeps the work). Someone else's subject or session, or an id that is not one, is the 404 page.
async function Study({ params }: { params: Promise<{ id: string; sid: string }> }) {
  await connection();
  await requireVerifiedSession();
  const { id, sid } = await params;
  const subject = await subjectForUpload(id);
  let loaded: Awaited<ReturnType<typeof loadSession>>;
  try {
    loaded = await loadSession(subject.id, sid);
  } catch (error) {
    if (error instanceof CoreStatusError) {
      if (error.status === 401) redirect("/login");
      if (error.status === 404 || error.status === 422) notFound();
    }
    throw error;
  }
  return <SessionLive sessionId={sid} subject={subject.name} stopHref="/today" docs={loaded.docs} initial={loaded.initial} />;
}

export default function StudySessionPage({ params }: { params: Promise<{ id: string; sid: string }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Study params={params} />
    </Suspense>
  );
}
