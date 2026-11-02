import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { QuestionList } from "@/components/question-list";
import { AppShell } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { loadQuestionList } from "@/lib/question-list";
import type { QuestionListOut } from "@/lib/question-list-types";
import { requireVerifiedSession } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";

export const metadata: Metadata = { title: "Luyện tập · Essity" };

// T8.2 (US-14 AC6; DESIGN §6.12): the subject's question bank with each question's readiness.
// Someone else's subject or a bad id is a 404 (subjectForUpload); a failed read shows an error with
// a retry link, not a broken page.
async function Practice({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  let list: QuestionListOut | null = null;
  try {
    list = await loadQuestionList(subject.id);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
  }
  return (
    <div className="mx-auto w-full max-w-(--col-session)">
      <h1 className="m-0 mb-6 font-display text-title">Luyện tập</h1>
      {list === null ? (
        <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
          <p className="m-0 font-semibold">Không tải được danh sách câu hỏi.</p>
          <p className="m-0 text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
          <a href={`/subjects/${subject.id}/practice`} className="mt-3 inline-flex min-h-11 items-center font-semibold underline">
            Thử lại
          </a>
        </div>
      ) : (
        <QuestionList subjectId={subject.id} list={list} />
      )}
    </div>
  );
}

export default function PracticePage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="mx-auto h-80 w-full max-w-(--col-session) rounded-sheet bg-sunken" />}>
        <Practice params={params} />
      </Suspense>
    </AppShell>
  );
}
