import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { SyllabusLive } from "@/components/syllabus/syllabus-live";
import { loadOutline } from "@/lib/outline";
import { requireVerifiedSession } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";
import type { OutlineOut } from "@/lib/syllabus/api";

export const metadata: Metadata = { title: "Đề cương · Essity" };

// T7.5 (US-13; DESIGN §6.6): the outline of a subject's main textbook. Someone else's subject or a
// bad id is a 404 (subjectForUpload); a failed read shows an error with a retry link, not a broken page.
async function Syllabus({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  let outline: OutlineOut | null = null;
  try {
    outline = await loadOutline(subject.id);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
  }
  if (outline === null) {
    return (
      <div className="mx-auto w-full max-w-(--col-session)">
        <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
          <p className="m-0 font-semibold">Không tải được đề cương.</p>
          <p className="m-0 text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
          <a href={`/subjects/${subject.id}/syllabus`} className="mt-3 inline-flex min-h-11 items-center font-semibold underline">
            Thử lại
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-(--col-session)">
      <SyllabusLive subjectId={subject.id} subjectName={subject.name} initial={outline} />
    </div>
  );
}

export default function SyllabusPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="mx-auto h-80 w-full max-w-(--col-session) rounded-sheet bg-sunken" />}>
        <Syllabus params={params} />
      </Suspense>
    </AppShell>
  );
}
