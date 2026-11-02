import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell } from "@/components/shells";
import { SubjectScreenBlock } from "@/components/subjects/subject-screen";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { dayLabel } from "@/lib/today-copy";
import { requireVerifiedSession } from "@/lib/session";
import { errorName, logError } from "@/lib/log";
import { CoreStatusError } from "@/lib/subjects";
import { getSuggestions } from "@/lib/today";
import { suggestionState } from "@/lib/today-adapt";
import type { SuggestionState } from "@/components/subjects/subject-suggestion";

export const metadata: Metadata = { title: "Môn học · Essity" };

// T7.13 (US-15 AC6, AC7; DESIGN §6.5): one subject with "Hôm nay nên học: mục X" or the
// "Gợi ý cho hôm nay" button. A failed read of the suggestions leaves the button, so the learner
// can still ask; someone else's subject or a bad id is the 404 page.
async function Subject({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  let state: SuggestionState;
  try {
    state = suggestionState(await getSuggestions(), subject.id, subject.days_until_exam);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
    logError("core-api call failed", { route: "today", error: errorName(error) });
    state = subject.days_until_exam < 0 ? { kind: "exam_over" } : { kind: "not_suggested" };
  }
  return (
    <div className="mx-auto flex w-full max-w-280 flex-col gap-6">
      <a href="/subjects" className="text-small">
        Môn học
      </a>
      <h1 className="m-0 font-display text-title wrap-anywhere">{subject.name}</h1>
      <p className="m-0 text-read text-ink-soft">
        Thi {dayLabel(subject.exam_date)}
        {subject.days_until_exam >= 0 ? ` (còn ${subject.days_until_exam} ngày)` : " (đã qua)"}
      </p>
      <SubjectScreenBlock subjectId={subject.id} subjectName={subject.name} state={state} />
    </div>
  );
}

export default function SubjectPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="mx-auto h-64 w-full max-w-280 rounded-sheet bg-sunken" />}>
        <Subject params={params} />
      </Suspense>
    </AppShell>
  );
}
