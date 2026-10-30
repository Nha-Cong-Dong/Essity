import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { TODAY_STATES } from "@/lib/fixtures/today-v2";

export const metadata: Metadata = { title: "Design preview: hôm nay v2 · Essity" };

// /today v2 with fixed data (T7.13a, ADR-0025): the real shell and TodayV2Screen, no core-api
// call and no session. `?state=` picks a state (default: the busiest). Closed outside development
// unless WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "busy" } = await searchParams;
  const today = TODAY_STATES[state] ?? TODAY_STATES.busy;
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto w-full max-w-280">
        <TodayV2Screen today={today} />
      </div>
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function TodayV2Fixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
