import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell, PageColumn } from "@/components/shells";
import { weekFromCells } from "@/components/today-v2/week-strip";
import { TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { TODAY_STATES } from "@/lib/fixtures/today-v2";

export const metadata: Metadata = { title: "Design preview: hôm nay v2 · Essity" };

// /today v2 with fixed data (T7.13a, ADR-0025): the real shell and TodayV2Screen, no core-api
// call and no session. `?state=` picks a state (default: the busiest). Closed outside development
// unless WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

// A fixed week (Mon..Sun of the fixture day) so the field poster shows both halves.
const WEEK = (day: string) =>
  weekFromCells(
    [
      { day: "2026-10-26", cardsSaved: 3, questionsAnswered: 1 },
      { day: "2026-10-27", cardsSaved: 4, questionsAnswered: 2 },
    ],
    day,
  );

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "busy" } = await searchParams;
  const today = TODAY_STATES[state] ?? TODAY_STATES.busy;
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="full">
        <TodayV2Screen today={today} preview week={WEEK(today.learning_day)} />
      </PageColumn>
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
