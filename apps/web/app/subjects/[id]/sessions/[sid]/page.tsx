import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { SessionLive } from "@/components/session-study/session-live";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { requireVerifiedSession } from "@/lib/session";
import { sectionParam } from "@/lib/session-study/entry";
import { freeSuggestion, sessionSuggestion } from "@/lib/session-study/suggestion";
import { getSubjectSuggestion, getSuggestions } from "@/lib/today";
import { loadSession } from "@/lib/session-study/load";
import { CoreStatusError } from "@/lib/subjects";

type Props = { params: Promise<{ id: string; sid: string }>; searchParams: Promise<{ section?: string | string[] }> };

export const metadata: Metadata = { title: "Buổi học · Essity" };

// T7.12 (US-02, US-02b; DESIGN.md §6.7): one session on one screen. It opens where the session
// is: a form, the reading still running, or the cards still to review (so leaving and coming back
// keeps the work). Someone else's subject or session, or an id that is not one, is the 404 page.
async function Study({ params, searchParams }: Props) {
  await connection();
  await requireVerifiedSession();
  const { id, sid } = await params;
  const section = sectionParam((await searchParams).section);
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
  // T7.19 F2: opened from a suggestion, the session is for that section (if it is still today's one).
  const suggestion = section ? await getSuggestions().then((all) => sessionSuggestion(all, subject.id, section)).catch(() => null) : null;
  // SESSION-END: no schedule for it today (or "Học tiếp"): free study, still on the next section of the
  // outline, so the suggestion shows and finishing counts toward progress.
  const free = suggestion ? null : await getSubjectSuggestion(subject.id).then(freeSuggestion).catch(() => null);
  return (
    <SessionLive
      sessionId={sid}
      subjectId={subject.id}
      subject={subject.name}
      stopHref="/today"
      account={<AccountSlot />}
      docs={loaded.docs}
      initial={loaded.initial}
      suggestion={suggestion ?? free?.suggestion}
      sectionId={suggestion ? (section ?? undefined) : free?.sectionId}
    />
  );
}

export default function StudySessionPage({ params, searchParams }: Props) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Study params={params} searchParams={searchParams} />
    </Suspense>
  );
}
