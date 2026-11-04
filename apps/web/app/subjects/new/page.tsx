import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AUTH_LINK } from "@/components/auth/fields";
import { Marker } from "@/components/notebook";
import { MarginRule } from "@/components/motifs";
import { Mascot } from "@/components/mascot";
import { AppShell, PageColumn } from "@/components/shells";
import { OutlineCard } from "@/components/subjects/outline-card";
import { StepIndicator } from "@/components/subjects/step-indicator";
import { Sheet } from "@/components/ui/sheet";
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
        <StepIndicator current={1} />
        <div className="flex items-end gap-4">
          <Sheet className="relative min-w-0 flex-1 p-5 pl-11 sm:p-8 sm:pl-14">
            <MarginRule />
            <h1 className="m-0 mb-2 font-display text-title">
              <Marker>Môn mới</Marker>
            </h1>
            <p className="m-0 mb-6 max-w-[48ch] text-read text-ink-soft">Đặt tên môn và ngày thi để app chia lịch học cho vừa sức.</p>
            <h2 className="m-0 mb-4 font-display text-lead">1. Thông tin</h2>
            <Suspense fallback={<div aria-busy="true" className="h-60" />}>
              <NewSubject />
            </Suspense>
          </Sheet>
          <div className="hidden shrink-0 min-[641px]:block">
            <Mascot pose="chuanbi" size="md" />
          </div>
        </div>
        <Sheet variant="tile" tone="rose" aria-labelledby="docs-next">
          <h2 id="docs-next" className="m-0 font-display text-lead">
            2. Tài liệu
          </h2>
          <p className="m-0 mt-2 text-read text-ink-soft">
            Sau khi tạo môn, bạn tải giáo trình chính, giáo trình phụ hoặc bộ câu hỏi (PDF).
          </p>
        </Sheet>
        <OutlineCard />
      </PageColumn>
    </AppShell>
  );
}
