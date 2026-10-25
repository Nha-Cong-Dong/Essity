import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell } from "@/components/shells";
import { SubjectsLoading } from "@/components/subjects/subjects-frame";
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
      {/* Each state draws the frame and its title, so "Tạo môn" can share the title's row (T2.3c plan G15). */}
      <Suspense fallback={<SubjectsLoading />}>
        <SignedInSubjects />
      </Suspense>
    </AppShell>
  );
}
