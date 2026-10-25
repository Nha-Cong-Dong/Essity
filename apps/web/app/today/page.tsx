import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { TodayFailed, TodayLoading, TodayScreen } from "@/components/today/today-screen";
import { errorName, logError } from "@/lib/log";
import { requireVerifiedSession } from "@/lib/session";
import { getToday, type Today } from "@/lib/today";

export const metadata: Metadata = { title: "Hôm nay · Essity" };

// "Phiên hôm nay" (T2.14, US-03, DESIGN.md §6.3): where the app lands after signing in (US-12
// AC7). The session is checked first, so a failing /v1/today never reads as signed out; it shows
// a notice with Thử lại and never redirects (plan K4).

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

async function Today() {
  await connection();
  await requireVerifiedSession();
  let today: Today;
  try {
    today = await getToday();
  } catch (error) {
    logError("core-api call failed", { route: "today", error: errorName(error) });
    return <TodayFailed />;
  }
  return <TodayScreen today={today} />;
}

export default function TodayPage() {
  return (
    <AppShell
      current="/today"
      account={
        <Suspense fallback={null}>
          <Account />
        </Suspense>
      }
    >
      <div className="mx-auto w-full max-w-280">
        <Suspense fallback={<TodayLoading />}>
          <Today />
        </Suspense>
      </div>
    </AppShell>
  );
}
