import type { Metadata } from "next";

import { AccountMenu } from "@/components/account-menu";
import { DocumentsFrame } from "@/components/documents/document-list";
import { TocTree, UnreadableNotice } from "@/components/documents/toc-view";
import { AppShell } from "@/components/shells";
import { toTree } from "@/lib/toc";

export const metadata: Metadata = { title: "Design preview: mục lục · Essity" };

// C4: the table of contents with fixed data. Closed outside development unless WEB_DESIGN_PREVIEW=1.
const ENTRIES = [
  { title: "Chương 1. Biến cố và xác suất", level: 0, page: 1 },
  { title: "1.1 Phép thử và không gian mẫu", level: 1, page: 3 },
  { title: "1.2 Xác suất có điều kiện", level: 1, page: 14 },
  { title: "Chương 2. Biến ngẫu nhiên", level: 0, page: 31 },
  { title: "2.1 Kỳ vọng và phương sai", level: 1, page: 36 },
  { title: "Chương 3. Ước lượng", level: 0, page: 60 },
];

export default function TocPreview() {
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <DocumentsFrame name="Giáo trình Xác suất thống kê">
        <p className="m-0 text-read text-ink-soft">Mục lục · 90 trang</p>
        <UnreadableNotice pages={[12, 13]} />
        <TocTree nodes={toTree(ENTRIES, 90)} />
      </DocumentsFrame>
    </AppShell>
  );
}
