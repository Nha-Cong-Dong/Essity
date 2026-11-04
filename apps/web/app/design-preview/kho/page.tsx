import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell, PageColumn } from "@/components/shells";
import { VaultView, type VaultViewData } from "@/components/vault/vault-view";

export const metadata: Metadata = { title: "Design preview: kho kiến thức · Essity" };

// V22 g2: the Kho kiến thức levels with fixed data (`?level=subjects|sessions`). Closed outside
// development unless WEB_DESIGN_PREVIEW=1 (proxy.ts).
const SUBJECTS: VaultViewData = {
  level: "subjects",
  subjects: [
    { id: "s1", name: "Mạng máy tính", sessions: 6, cards: 41 },
    { id: "s2", name: "Xác suất thống kê", sessions: 3, cards: 17 },
    { id: "s3", name: "Cấu trúc dữ liệu và giải thuật nâng cao", sessions: 2, cards: 9 },
  ],
};
const SESSIONS: VaultViewData = {
  level: "sessions",
  graphs: [],
  sessions: [
    { id: "a", title: "Tầng giao vận: TCP và UDP", studied_on: "04/11/2026", cards: 8 },
    { id: "b", title: "Định tuyến trong mạng", studied_on: "01/11/2026", cards: 6 },
    { id: "c", title: "Tầng ứng dụng: HTTP", studied_on: "28/10/2026", cards: 5 },
  ],
};

async function Fixture({ searchParams }: { searchParams: Promise<{ level?: string }> }) {
  const { level } = await searchParams;
  return (
    <AppShell current="/kho-kien-thuc" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="wide">
        <VaultView view={level === "sessions" ? SESSIONS : SUBJECTS} subjectId="s1" />
      </PageColumn>
    </AppShell>
  );
}

export default function KhoFixture(props: { searchParams: Promise<{ level?: string }> }) {
  return (
    <Suspense fallback={null}>
      <Fixture {...props} />
    </Suspense>
  );
}
