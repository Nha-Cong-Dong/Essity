import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { StatsLoading, StatsScreen } from "@/components/stats/stats-screen";
import { errorName, logError } from "@/lib/log";
import { requireVerifiedSession } from "@/lib/session";
import { getStats } from "@/lib/stats-api";

export const metadata: Metadata = { title: "Thống kê · Essity" };

// "Thống kê" (T9.5, US-10, DESIGN §6.13): every subject, or one with ?subject=. The session is
// checked first, so a failing /v1/stats never reads as signed out; it shows the notice with
// Thử lại and never redirects.

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

const EMPTY = { today: "", subjects: [], cells: [] };

async function Stats({ searchParams }: { searchParams: Promise<{ subject?: string | string[] }> }) {
  await connection();
  await requireVerifiedSession();
  const { subject } = await searchParams;
  let stats: Awaited<ReturnType<typeof getStats>>;
  try {
    stats = await getStats(typeof subject === "string" ? subject : undefined);
  } catch (error) {
    logError("core-api call failed", { route: "stats", error: errorName(error) });
    return <StatsScreen view={EMPTY} mode="error" />;
  }
  return <StatsScreen view={stats.view} subject={stats.subject} />;
}

export default function StatsPage(props: { searchParams: Promise<{ subject?: string | string[] }> }) {
  return (
    <AppShell
      current="/stats"
      account={
        <Suspense fallback={null}>
          <Account />
        </Suspense>
      }
    >
      <div className="mx-auto w-full max-w-280">
        <Suspense fallback={<StatsLoading />}>
          <Stats {...props} />
        </Suspense>
      </div>
    </AppShell>
  );
}
