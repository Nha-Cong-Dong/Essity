import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { COMMAND_STATE_IDS } from "@/lib/fixtures/command-bar";

import { CommandPreview } from "./preview";

export const metadata: Metadata = { title: "Design preview: thanh lệnh · Essity" };

// The command bar (T9.3a) inside a mock subject header, with fixed data and no core-api. `?state=`
// picks a state (default: idle). Live routes are not touched. Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "idle" } = await searchParams;
  const known = COMMAND_STATE_IDS.find((id) => id === state) ?? "idle";
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <CommandPreview state={known} />
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function CommandBarFixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
