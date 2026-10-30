import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { GraphScreen } from "@/components/graph/graph-screen";
import { AppShell } from "@/components/shells";
import { GRAPH_STATE_IDS } from "@/lib/fixtures/graph";

export const metadata: Metadata = { title: "Design preview: đồ thị · Essity" };

// The Đồ thị screen (T9.10a) with fixed data and no core-api. `?state=` picks a state (default:
// few); `?view=list`, `?section=` and `?edge=` set the list switch and the filters as the live
// /subjects/[id]/graph will. The live route and the header nav are not touched. Closed outside
// development unless WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "few" } = await searchParams;
  const known = GRAPH_STATE_IDS.find((id) => id === state) ?? "few";
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <GraphScreen key={known} state={known} />
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function GraphFixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
