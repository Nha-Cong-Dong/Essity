import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { DocumentList, DocumentsFrame } from "@/components/documents/document-list";
import { AppShell } from "@/components/shells";

export const metadata: Metadata = { title: "Design preview: tài liệu · Essity" };

// C4: the document list with fixed data (every state), `?empty=1` for the empty one. Closed outside
// development unless WEB_DESIGN_PREVIEW=1 (proxy.ts).
const SUBJECT = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOCS = [
  { id: "d1", short_name: "Giáo trình Xác suất thống kê", status: "indexed", page_count: 320, unreadable_pages: [], failure_reason: null, role: "textbook" },
  { id: "d2", short_name: "Slide chương 3", status: "indexed", page_count: 54, unreadable_pages: [12, 13, 40], failure_reason: null },
  { id: "d3", short_name: "Ảnh vở tuần 5", status: "pending", page_count: null, unreadable_pages: [], failure_reason: null },
  { id: "d4", short_name: "Đề cương cũ", status: "failed", page_count: null, unreadable_pages: [], failure_reason: "encrypted" },
];

async function Fixture({ searchParams }: { searchParams: Promise<{ empty?: string }> }) {
  const empty = (await searchParams).empty === "1";
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <DocumentsFrame name="Xác suất thống kê">
        <DocumentList subjectId={SUBJECT} docs={empty ? [] : DOCS} />
      </DocumentsFrame>
    </AppShell>
  );
}

export default function DocumentsPreview(props: { searchParams: Promise<{ empty?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
