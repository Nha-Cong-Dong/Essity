import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AUTH_LINK } from "@/components/auth/fields";
import { Mascot } from "@/components/mascot";
import { AppShell, PageColumn } from "@/components/shells";
import { NewSubjectForm } from "@/components/subjects/new-subject-form";
import { exampleFor } from "@/lib/exam-date";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Tạo môn · Essity" };

// T1.20, DESIGN.md §6.8: a new subject is a notebook cover with a label of two fields (US-01 AC1).
async function NewSubject() {
  await connection();
  const me = await requireVerifiedSession();
  // The example follows the user's learning day, not the server's clock (risk register R24).
  return <NewSubjectForm example={exampleFor(new Date(), me.timezone, me.day_start_hour)} />;
}

export default function NewSubjectPage() {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <PageColumn width="read" className="flex flex-col gap-6">
        <a href="/subjects" className={AUTH_LINK}>
          Môn học
        </a>
        <header className="flex items-end justify-between gap-4">
          <div className="flex flex-col gap-2">
            <p className="m-0 text-small font-semibold text-ink-soft">Bước 1 trên 2</p>
            <h1 className="m-0 font-display text-title">Thêm môn mới</h1>
            <p className="m-0 max-w-[48ch] text-read text-ink-soft">
              Đặt tên môn và ngày thi. Ngày thi giúp app chia lịch học cho vừa sức.
            </p>
          </div>
          <Mascot pose="chuanbi" size="sm" />
        </header>
        <section className="rounded-sheet bg-sunken p-6 max-[480px]:p-4">
          <Suspense fallback={<div aria-busy="true" className="h-60" />}>
            <NewSubject />
          </Suspense>
        </section>
      </PageColumn>
    </AppShell>
  );
}
