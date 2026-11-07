import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { GraphScreen } from "@/components/graph/graph-screen";
import { AppShell } from "@/components/shells";
import { GRAPH_STATE_IDS, graphFixture } from "@/lib/fixtures/graph";

export const metadata: Metadata = { title: "Design preview: đồ thị · Essity" };

// The Đồ thị screen (T9.10a) with fixed data and no core-api. `?state=` picks a state (default:
// few); `?view=list`, `?section=` and `?edge=` set the list switch and the filters as the live
// /subjects/[id]/graph will. The live route and the header nav are not touched. Closed outside
// development unless WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string; live?: string }> }) {
  const { state = "few", live } = await searchParams;
  const known = GRAPH_STATE_IDS.find((id) => id === state) ?? "few";
  // `?live=1` (T9.10): the screen as /subjects/[id]/graph builds it (real-data props: no unlink).
  const data = graphFixture("few").data;
  if (live === "1" && data) {
    return (
      <AppShell current="/graph" account={<AccountMenu email="xem-thu@example.com" />}>
        <GraphScreen live={{ subjectId: "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f", subjectName: "Mạng máy tính", data }} />
      </AppShell>
    );
  }
  return (
    <AppShell current="/graph" account={<AccountMenu email="xem-thu@example.com" />}>
      <GraphScreen key={known} state={known} />
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function GraphFixture(props: { searchParams: Promise<{ state?: string; live?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
