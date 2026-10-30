import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { PracticeScreen } from "@/components/practice/practice-screen";
import { AppShell } from "@/components/shells";
import { PRACTICE_STATE_IDS } from "@/lib/fixtures/practice";

export const metadata: Metadata = { title: "Design preview: luyện tập · Essity" };

// The Luyện tập screen (T8.7a) with fixed data and no core-api. `?state=` picks a state (default:
// home). The live /subjects/[id]/practice is not touched. Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "home" } = await searchParams;
  const known = PRACTICE_STATE_IDS.find((id) => id === state) ?? "home";
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto w-full max-w-280">
        <PracticeScreen key={known} state={known} />
      </div>
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function PracticeFixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
