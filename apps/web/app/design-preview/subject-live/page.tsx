import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell, PageColumn } from "@/components/shells";
import { SubjectEntryRow } from "@/components/subjects/subject-entry-row";
import { SubjectScreenBlock } from "@/components/subjects/subject-screen";
import { entryRow } from "@/lib/subject-entries";
import { SUBJECT_FIXTURE, SUBJECT_STATES } from "@/lib/fixtures/today-v2";

export const metadata: Metadata = { title: "Design preview: màn môn thật · Essity" };

// T7.13: the subject block as the real page builds it (SubjectScreenBlock, whose button calls
// /api/subjects/{id}/suggestion). The e2e answers that call itself (page.route), so the main flow
// runs without core-api. Closed outside development unless WEB_DESIGN_PREVIEW=1.
// The row as the real page builds it from API data (T7.13b): fixed numbers, no core-api call.
const ENTRIES = entryRow(SUBJECT_FIXTURE.id, {
  outline: {
    subject_id: SUBJECT_FIXTURE.id,
    document: { id: "d1", page_count: 20, short_name: "Giáo trình" },
    progress: 0.5,
    reason: null,
    temporary: false,
    remaining_chapters: 1,
    sections: ["1", "2"].map((id, i) => ({
      id, parent_id: null, title: id, first_page: 1, last_page: 10, weight: 10, unit: "page" as const,
      source: "bookmark" as const, excluded: false, excluded_effective: false, progress: i === 0 ? 1 : 0,
      studied: i === 0, learned: i === 0, children: [],
    })),
  },
  questions: { ready: 5, total: 9 },
  graphCards: 12,
});

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "not-suggested" } = await searchParams;
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="full" className="flex flex-col gap-6">
        <h1 className="m-0 font-display text-title wrap-anywhere">{SUBJECT_FIXTURE.name}</h1>
        <SubjectScreenBlock
          subjectId={SUBJECT_FIXTURE.id}
          subjectName={SUBJECT_FIXTURE.name}
          state={SUBJECT_STATES[state] ?? SUBJECT_STATES["not-suggested"]}
        />
        <SubjectEntryRow entries={ENTRIES} />
      </PageColumn>
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
