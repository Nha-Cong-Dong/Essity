import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { StatsScreen } from "@/components/stats/stats-screen";
import { AppShell } from "@/components/shells";
import { STATS_STATE_IDS } from "@/lib/fixtures/stats";

export const metadata: Metadata = { title: "Design preview: thống kê · Essity" };

// The Thống kê screen (T9.5a) with fixed data and no core-api. `?state=` picks a state (default:
// full-year) and `?subject=` filters one subject, as the live /stats will. The live route and the
// header nav are not touched. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts,
// lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "full-year" } = await searchParams;
  const known = STATS_STATE_IDS.find((id) => id === state) ?? "full-year";
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <StatsScreen key={known} state={known} />
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function StatsFixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
