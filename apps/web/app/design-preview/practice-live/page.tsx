import type { Metadata } from "next";

import { AccountMenu } from "@/components/account-menu";
import { PracticeLive } from "@/components/practice/practice-live";
import { AppShell, PageColumn } from "@/components/shells";
import { LIVE_LIST, LIVE_SUBJECT, LIVE_TYPES } from "@/lib/fixtures/practice-live";

export const metadata: Metadata = { title: "Design preview: luyện tập thật · Essity" };

// T8.7: the Luyện tập screen as the real page builds it (PracticeLive, whose buttons call
// /api/practice/*). The e2e answers those calls itself (page.route), so the main flow runs without
// core-api. Closed outside development unless WEB_DESIGN_PREVIEW=1.
export default function PracticeLivePreview() {
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="wide">
        <PracticeLive
          subjectId={LIVE_SUBJECT.id}
          subjectName={LIVE_SUBJECT.name}
          list={LIVE_LIST}
          types={LIVE_TYPES}
          listPath="/design-preview/practice-live"
        />
      </PageColumn>
    </AppShell>
  );
}
