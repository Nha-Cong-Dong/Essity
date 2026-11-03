import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { NewSessionEntry } from "@/components/session-study/new-entry";
import { AppShell, PageColumn } from "@/components/shells";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Ghi buổi học · Essity" };

// The session check stays in the page (source-rules: every private page asks core-api).
async function Guarded(props: { params: Promise<{ id: string }>; searchParams: Promise<{ session?: string | string[]; v1?: string | string[] }> }) {
  await connection();
  await requireVerifiedSession();
  return <NewSessionEntry {...props} />;
}

export default function NewSessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ session?: string | string[]; v1?: string | string[] }>;
}) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<PageColumn width="full" aria-busy="true" className="h-80 rounded-sheet bg-sunken" />}>
        <Guarded params={params} searchParams={searchParams} />
      </Suspense>
    </AppShell>
  );
}
