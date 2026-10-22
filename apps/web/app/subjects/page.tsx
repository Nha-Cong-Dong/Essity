import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { Marker } from "@/components/notebook";
import { AppShell } from "@/components/shells";
import { SubjectList } from "@/components/subjects/subject-list";
import { Button } from "@/components/ui/button";
import { requireVerifiedSession } from "@/lib/session";
import { listSubjects, type Subject } from "@/lib/subjects";

export const metadata: Metadata = { title: "Môn học · Essity" };

// T1.20, DESIGN.md §6.8: the subjects, each with its exam date and the days left; edited in place
// (plan K2). One primary button: "Tạo môn" in the header, or in the empty state.
async function Subjects() {
  await connection();
  await requireVerifiedSession();
  let subjects: Subject[];
  try {
    subjects = await listSubjects();
  } catch {
    return (
      <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
        <p className="m-0 font-semibold" data-copy="tam">
          Không tải được danh sách môn.
        </p>
        <p className="m-0 text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
        <Button render={<a href="/subjects" />} nativeButton={false} variant="secondary" className="mt-3">
          Thử lại
        </Button>
      </div>
    );
  }
  const listed = subjects.map(({ id, name, exam_date, days_until_exam }) => ({ id, name, exam_date, days_until_exam }));
  return (
    <>
      {listed.length > 0 && (
        <div className="-mt-16 mb-6 flex justify-end">
          <Button render={<a href="/subjects/new" />} nativeButton={false}>
            Tạo môn
          </Button>
        </div>
      )}
      <SubjectList subjects={listed} />
    </>
  );
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
              <p className="sr-only" role="status">
                Đang tải danh sách môn.
              </p>
            </div>
          }
        >
          <Subjects />
        </Suspense>
      </div>
    </AppShell>
  );
}
