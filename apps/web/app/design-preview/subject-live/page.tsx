import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { SubjectScreenBlock } from "@/components/subjects/subject-screen";
import { SUBJECT_FIXTURE, SUBJECT_STATES } from "@/lib/fixtures/today-v2";

export const metadata: Metadata = { title: "Design preview: màn môn thật · Essity" };

// T7.13: the subject block as the real page builds it (SubjectScreenBlock, whose button calls
// /api/subjects/{id}/suggestion). The e2e answers that call itself (page.route), so the main flow
// runs without core-api. Closed outside development unless WEB_DESIGN_PREVIEW=1.
async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "not-suggested" } = await searchParams;
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto flex w-full max-w-280 flex-col gap-6">
        <h1 className="m-0 font-display text-title wrap-anywhere">{SUBJECT_FIXTURE.name}</h1>
        <SubjectScreenBlock
          subjectId={SUBJECT_FIXTURE.id}
          subjectName={SUBJECT_FIXTURE.name}
          state={SUBJECT_STATES[state] ?? SUBJECT_STATES["not-suggested"]}
        />
      </div>
    </AppShell>
  );
}

export default function SubjectLivePreview(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
