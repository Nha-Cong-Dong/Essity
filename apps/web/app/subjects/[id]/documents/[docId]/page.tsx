import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { DocumentsFrame } from "@/components/documents/document-list";
import { TocNotReady, TocTree, TocUnreadable, UnreadableNotice } from "@/components/documents/toc-view";
import { AppShell } from "@/components/shells";
import { type Document, readDocument, readToc, type TocResult } from "@/lib/documents";
import { requireVerifiedSession } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";
import { toTree } from "@/lib/toc";

export const metadata: Metadata = { title: "Mục lục · Essity" };

// T4.9 (US-02 AC2): the table of contents of one document. A document that is not the user's (or
// not in this subject) is a 404; a toc that is not toc.v1 shows "chưa đọc được", never a broken page.
async function Toc({ params }: { params: Promise<{ id: string; docId: string }> }) {
  await connection();
  await requireVerifiedSession();
  const { id, docId } = await params;
  let doc: Document | null = null;
  let toc: TocResult = { kind: "not_indexed" };
  try {
    doc = await readDocument(docId);
    if (doc.status === "indexed") toc = await readToc(docId);
  } catch (error) {
    if (error instanceof CoreStatusError) {
      if (error.status === 401) redirect("/login");
      if (error.status === 404) notFound();
    }
  }
  if (doc === null) {
    return (
      <DocumentsFrame name="Mục lục">
        <TocUnreadable />
      </DocumentsFrame>
    );
  }
  if (doc.subject_id.toLowerCase() !== id.toLowerCase()) notFound();
  return (
    <DocumentsFrame name={doc.short_name}>
      <p className="m-0 mb-4 text-ink-soft">Mục lục{doc.page_count !== null ? ` · ${doc.page_count} trang` : ""}</p>
      {toc.kind === "ok" && (
        <>
          <UnreadableNotice pages={doc.unreadable_pages} />
          <TocTree nodes={toTree(toc.entries, doc.page_count)} />
        </>
      )}
      {toc.kind === "unreadable" && <TocUnreadable />}
      {toc.kind === "not_indexed" && <TocNotReady />}
    </DocumentsFrame>
  );
}

export default function TocPage({ params }: { params: Promise<{ id: string; docId: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="mx-auto h-80 w-full max-w-220 rounded-sheet bg-sunken" />}>
        <Toc params={params} />
      </Suspense>
    </AppShell>
  );
}
