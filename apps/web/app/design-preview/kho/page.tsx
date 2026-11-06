import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell, PageColumn } from "@/components/shells";
import { VaultView, type VaultViewData } from "@/components/vault/vault-view";

export const metadata: Metadata = { title: "Design preview: kho kiến thức · Essity" };

// V22 g2: the Kho kiến thức levels with fixed data (`?level=subjects|sessions|cards`). Closed outside
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
  subjectName: "Xác suất thống kê",
  sessions: [
    { id: "a", title: "Tầng giao vận: TCP và UDP", studied_on: "04/11/2026", cards: 8 },
    { id: "b", title: "Định tuyến trong mạng", studied_on: "01/11/2026", cards: 6 },
    { id: "c", title: "Tầng ứng dụng: HTTP", studied_on: "28/10/2026", cards: 5 },
  ],
};

const CARDS: VaultViewData = {
  level: "cards",
  title: "Quy tắc đếm",
  subjectName: "Xác suất thống kê",
  cards: [
    ["Quy tắc cộng", "Hai phương án không trùng nhau: A có m cách, B có n cách thì tổng cộng có m + n cách."],
    ["Quy tắc nhân", "Việc gồm hai bước liên tiếp: bước 1 có m cách, bước 2 có n cách thì cả việc có m × n cách."],
    ["Hoán vị", "Số cách xếp n phần tử khác nhau thành một hàng là n!."],
    ["Chỉnh hợp", "Chọn k phần tử từ n rồi xếp thứ tự: A(n,k) = n!/(n−k)!."],
    ["Tổ hợp", "Chọn k phần tử từ n, không phân biệt thứ tự: C(n,k) = n!/(k!(n−k)!)."],
  ].map(([title, content], i) => ({ id: `c${i}`, title, content, kind: "concept", anchors: [] })),
};

async function Fixture({ searchParams }: { searchParams: Promise<{ level?: string }> }) {
  const { level } = await searchParams;
  return (
    <AppShell current="/kho-kien-thuc" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="wide">
        <VaultView view={level === "cards" ? CARDS : level === "sessions" ? SESSIONS : SUBJECTS} subjectId="s1" />
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
