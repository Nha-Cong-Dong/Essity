import type { Metadata } from "next";

import { AccountMenu } from "@/components/account-menu";
import { KnowledgeGraph } from "@/components/graph/knowledge-graph";
import { AppShell, PageColumn } from "@/components/shells";
import { graphFixture } from "@/lib/fixtures/graph";

export const metadata: Metadata = { title: "Design preview: đồ thị mọi môn · Essity" };

// The /graph page as it draws (KnowledgeGraph over several subjects) with fixed data and no core-api.
// Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts).
export default function GraphAllPreview() {
  const data = graphFixture("few").data;
  if (!data) return null;
  const second = {
    sections: data.sections,
    cards: data.cards.slice(0, 3).map((c) => ({ ...c, id: `b-${c.id}`, title: `${c.title} (XS)` })),
    edges: data.edges
      .filter((e) => data.cards.slice(0, 3).some((c) => c.id === e.from) && data.cards.slice(0, 3).some((c) => c.id === e.to))
      .map((e) => ({ ...e, id: `b-${e.id}`, from: `b-${e.from}`, to: `b-${e.to}` })),
  };
  return (
    <AppShell current="/graph" account={<AccountMenu email="xem-thu@example.com" />}>
      <PageColumn width="full" className="flex flex-col">
        <h1 className="sr-only">Đồ thị tri thức</h1>
        <KnowledgeGraph
          graphs={[
            { id: "s1", name: "Mạng máy tính", data },
            { id: "s2", name: "Xác suất thống kê", data: second },
          ]}
        />
      </PageColumn>
    </AppShell>
  );
}
