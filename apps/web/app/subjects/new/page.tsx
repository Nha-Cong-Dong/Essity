import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AUTH_LINK } from "@/components/auth/fields";
import { NhanVo, NotebookCover } from "@/components/notebook";
import { AppShell } from "@/components/shells";
import { NewSubjectForm } from "@/components/subjects/new-subject-form";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Tạo môn · Essity" };

// T1.20, DESIGN.md §6.8: a new subject is a notebook cover with a label of two fields (US-01 AC1).
async function NewSubject() {
  await connection();
  await requireVerifiedSession();
  return <NewSubjectForm />;
}

export default function NewSubjectPage() {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <div className="mx-auto flex w-full max-w-160 flex-col gap-4">
        <a href="/subjects" className={AUTH_LINK}>
          Môn học
        </a>
        <NotebookCover title="Môn mới">
          <NhanVo>
            <Suspense fallback={<div aria-busy="true" className="h-60" />}>
              <NewSubject />
            </Suspense>
          </NhanVo>
        </NotebookCover>
      </div>
    </AppShell>
  );
}
