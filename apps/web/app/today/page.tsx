import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { NhanVo, NotebookCover } from "@/components/notebook";
import { AppShell } from "@/components/shells";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Hôm nay · Essity" };

// Placeholder for "Phiên hôm nay" (T2.14 fills it): where the app lands after signing in (AC7).
// Shows the "new account, no subject yet" state of DESIGN.md §6.3.

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

async function Today() {
  await connection();
  await requireVerifiedSession();
  return (
    <NotebookCover title="Hôm nay">
      <NhanVo>
        <p className="m-0">Chưa có môn nào. Tạo môn đầu tiên bằng tên và ngày thi.</p>
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
        <Suspense fallback={null}>
          <Today />
        </Suspense>
      </div>
    </AppShell>
  );
}
