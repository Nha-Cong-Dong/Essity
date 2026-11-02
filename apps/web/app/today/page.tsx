import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { TodayV2Failed, TodayV2Loading, TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { errorName, logError } from "@/lib/log";
import { requireVerifiedSession } from "@/lib/session";
import { getToday } from "@/lib/today";
import { type TodayApi, toTodayV2 } from "@/lib/today-adapt";

export const metadata: Metadata = { title: "Hôm nay · Essity" };

// "Hôm nay" v2 (T7.13, US-03, US-15, DESIGN.md §6.2; T2.14 built v1): where the app lands after signing in (US-12
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
  let today: TodayApi;
  try {
    today = await getToday();
  } catch (error) {
    logError("core-api call failed", { route: "today", error: errorName(error) });
    return <TodayV2Failed />;
  }
  return <TodayV2Screen today={toTodayV2(today)} />;
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
        <Suspense fallback={<TodayV2Loading />}>
          <Today />
        </Suspense>
      </div>
    </AppShell>
  );
}
