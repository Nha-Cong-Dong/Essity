import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { StatsScreen } from "@/components/stats/stats-screen";
import { AppShell } from "@/components/shells";
import { STATS_STATE_IDS, statsFixture } from "@/lib/fixtures/stats";
import { buildGrid } from "@/lib/stats";

export const metadata: Metadata = { title: "Design preview: thống kê · Essity" };

// The Thống kê screen (T9.5a) with fixed data and no core-api. `?state=` picks a state (default:
// full-year) and `?subject=` filters one subject, as the live /stats will. The live route and the
// header nav are not touched. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts,
// lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string; subject?: string }> }) {
  const { state = "full-year", subject = "" } = await searchParams;
  const known = STATS_STATE_IDS.find((id) => id === state) ?? "full-year";
  const data = statsFixture(known);
  const chosen = data.subjects.find((s) => s.id === subject)?.id;
  const view = { today: data.today, subjects: data.subjects, cells: buildGrid(data.subjects, data.events, data.today, chosen) };
  const mode = known === "loading" || known === "error" ? known : "ready";
  return (
    <AppShell current="/stats" account={<AccountMenu email="xem-thu@example.com" />}>
      <StatsScreen key={`${known}:${chosen ?? ""}`} view={view} subject={chosen ?? ""} mode={mode} />
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function StatsFixture(props: { searchParams: Promise<{ state?: string; subject?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
