import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { LogSession } from "@/components/log-session";
import { PageFold } from "@/components/motifs";
import { AppShell } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { Sheet } from "@/components/ui/sheet";
import { requireVerifiedSession } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

export const metadata: Metadata = { title: "Ghi buổi học · Essity" };

// T4.13a (US-02 AC1, DESIGN.md §6.10): one page, a sentence and what the app understood. Someone
// else's subject, or an id that is not one, shows the not-found page (same check as the upload
// step); a session that ended goes to /login.
async function Log({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ session?: string | string[] }>;
}) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  const { session } = await searchParams;
  const saved = typeof session === "string" && isSubjectId(session) ? session : undefined;
  return (
    <div className="mx-auto w-full max-w-220">
      <a href={`/subjects/${subject.id}/documents`} className="inline-flex items-center gap-1 text-meta text-ink-soft">
        ← {subject.name}
      </a>
      <Sheet className="relative mt-3" aria-labelledby="log-title">
        <PageFold />
        <LogSession subjectId={subject.id} subjectName={subject.name} savedSessionId={saved} />
      </Sheet>
    </div>
  );
}

export default function NewSessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ session?: string | string[] }>;
}) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="mx-auto h-80 w-full max-w-220 rounded-sheet bg-sunken" />}>
        <Log params={params} searchParams={searchParams} />
      </Suspense>
    </AppShell>
  );
}
