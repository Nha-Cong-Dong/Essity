import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell } from "@/components/shells";
import { CreateFrame } from "@/components/subjects/create-steps";
import { NewSubjectForm } from "@/components/subjects/new-subject-form";
import { exampleFor } from "@/lib/exam-date";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Tạo môn · Essity" };

// T1.20, DESIGN.md §6.8; DESIGN-V4: "Tạo môn" step 1, two fields on a white sheet beside the steps (US-01 AC1).
async function NewSubject() {
  await connection();
  const me = await requireVerifiedSession();
  // The example follows the user's learning day, not the server's clock (risk register R24).
  return <NewSubjectForm example={exampleFor(new Date(), me.timezone, me.day_start_hour)} />;
}

export default function NewSubjectPage() {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <CreateFrame current={1}>
        <Suspense fallback={<div aria-busy="true" className="h-60" />}>
          <NewSubject />
        </Suspense>
      </CreateFrame>
    </AppShell>
  );
}
