import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { NhanVo, NotebookCover } from "@/components/notebook";
import { AppShell } from "@/components/shells";
import { TodayNote } from "@/components/today-note";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Hôm nay · Essity" };

// Placeholder for "Phiên hôm nay" (T2.14 fills it): where the app lands after signing in (AC7).
// Plan K16: what it says follows has_subjects; a failing /v1/me throws, so it never guesses.

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

async function Today() {
  await connection();
  const me = await requireVerifiedSession();
  return (
    <NotebookCover title="Hôm nay">
      <NhanVo>
        <TodayNote hasSubjects={me.has_subjects} />
      </NhanVo>
    </NotebookCover>
  );
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
      <div className="flex justify-center">
        {/* Loading: a skeleton the shape of the cover (DESIGN.md §6.3), never a page spinner. */}
        <Suspense
          fallback={
            <div
              aria-busy="true"
              className="h-65 w-full max-w-155 rounded-sheet bg-sunken"
            />
          }
        >
          <Today />
        </Suspense>
      </div>
    </AppShell>
  );
}
