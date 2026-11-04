import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { EmptyState } from "@/components/empty-state";
import { KnowledgeGraph } from "@/components/graph/knowledge-graph";
import { AppShell, PageColumn } from "@/components/shells";
import type { SubjectGraph } from "@/lib/graph-multi";
import { loadAllGraphs } from "@/lib/graph-multi-load";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Đồ thị · Essity" };

// V16: the graph of every subject, one colour per subject.
async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

async function Graphs() {
  await connection();
  await requireVerifiedSession();
  let graphs: SubjectGraph[] | null = null;
  try {
    graphs = await loadAllGraphs();
  } catch {
    graphs = null;
  }
  if (graphs === null) return <EmptyState title="Chưa mở được đồ thị." hint="Tải lại trang sau ít phút." />;
  if (graphs.length === 0) {
    return (
      <EmptyState
        mascot="vui"
        title="Chưa có môn nào."
        hint="Tạo môn và ghi buổi học đầu tiên, các thẻ sẽ hiện thành đồ thị ở đây."
        action={
          <a href="/subjects/new" className="text-body font-semibold">
            Tạo môn
          </a>
        }
      />
    );
  }
  return <KnowledgeGraph graphs={graphs} />;
}

export default function GraphPage() {
  return (
    <AppShell
      current="/graph"
      account={
        <Suspense fallback={null}>
          <Account />
        </Suspense>
      }
    >
      <PageColumn width="full" className="flex flex-col gap-4">
        <h1 className="m-0 font-display text-display">Đồ thị tri thức</h1>
        <Suspense fallback={<div aria-busy="true" className="h-80 w-full rounded-sheet bg-sunken" />}>
          <Graphs />
        </Suspense>
      </PageColumn>
    </AppShell>
  );
}
