import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { UploadStep } from "@/components/subjects/upload-step";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Tải tài liệu · Essity" };

// T1.20, US-01 AC7 (plan K5): the step after "Tạo môn", at its own URL so a reload keeps it and
// does not create the subject twice. Someone else's subject, or an id that is not one, shows the
// not-found page. Inside Suspense the status stays 200 once the shell has streamed (Next's
// streaming docs); accepted (risk register R19): the page needs a session, has no SEO, and every
// case looks the same, so nothing about other people's subjects leaks.
async function Upload({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  return <UploadStep name={subject.name} />;
}

export default function UploadPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <div className="flex justify-center">
        <Suspense fallback={<div aria-busy="true" className="h-80 w-full max-w-220 rounded-sheet bg-sunken" />}>
          <Upload params={params} />
        </Suspense>
      </div>
    </AppShell>
  );
}
