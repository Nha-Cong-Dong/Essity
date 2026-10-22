import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { Marker } from "@/components/notebook";
import { AppShell } from "@/components/shells";
import { Subjects } from "@/components/subjects/subjects-loader";
import { exampleFor } from "@/lib/exam-date";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Môn học · Essity" };

// T1.20, DESIGN.md §6.8: the subjects, each with its exam date and the days left; edited in place
// (plan K2).
async function SignedInSubjects() {
  await connection();
  const me = await requireVerifiedSession();
  return <Subjects example={exampleFor(new Date(), me.timezone, me.day_start_hour)} />;
}

export default function SubjectsPage() {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <div className="mx-auto flex w-full max-w-220 flex-col">
        <h1 className="m-0 mb-8 font-display text-title">
          <Marker>Môn học</Marker>
        </h1>
        <Suspense
          fallback={
            <div aria-busy="true" className="flex flex-col gap-4">
              <div className="h-20 rounded-sheet bg-sunken" />
              <div className="h-20 rounded-sheet bg-sunken" />
              <p className="sr-only" role="status" data-copy="tam">
                Đang tải danh sách môn.
              </p>
            </div>
          }
        >
          <SignedInSubjects />
        </Suspense>
      </div>
    </AppShell>
  );
}
