import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { DocumentList, DocumentsFrame } from "@/components/documents/document-list";
import { Block } from "@/components/screen-kit";
import { AppShell, PageColumn } from "@/components/shells";
import { Button } from "@/components/ui/button";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { type Document, listDocuments } from "@/lib/documents";
import { CoreStatusError } from "@/lib/subjects";
import { requireVerifiedSession } from "@/lib/session";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Tài liệu · Essity" };

// T4.9 (US-01): a subject's documents and their state. Someone else's subject or a bad id is a 404
// (subjectForUpload, plan K5); a failed read shows the mockup's error, not a broken page.
async function Documents({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  let docs: Document[] | null = null;
  try {
    docs = await listDocuments(subject.id);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
  }
  if (docs !== null) {
    return (
      <DocumentsFrame name={subject.name}>
        <DocumentList subjectId={subject.id} docs={docs} />
      </DocumentsFrame>
    );
  }
  return (
    <DocumentsFrame name={subject.name}>
      <Block as="section" tier="sheet" role="alert" className="flex flex-col items-start gap-2">
        <p className="m-0 text-lead">Không tải được môn này.</p>
        <p className="m-0 text-body text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
        <Button render={<a href={`/subjects/${subject.id}/documents`} />} nativeButton={false} variant="quiet" className="mt-3">
          Thử lại
        </Button>
      </Block>
    </DocumentsFrame>
  );
}

export default function SubjectPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<PageColumn width="full" aria-busy="true" className="h-80 rounded-tile bg-sunken motion-safe:animate-pulse" />}>
        <Documents params={params} />
      </Suspense>
    </AppShell>
  );
}
