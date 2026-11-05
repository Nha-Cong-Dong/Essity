import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { GraphScreen } from "@/components/graph/graph-screen";
import { AppShell, PageColumn } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import type { GraphData } from "@/lib/graph";
import { loadGraph } from "@/lib/graph-load";
import { requireVerifiedSession } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";

export const metadata: Metadata = { title: "Đồ thị · Essity" };

// T9.10 (US-19 AC3, AC4, AC6; DESIGN §6.15): the graph of one subject on real data. Someone else's
// subject or a bad id is the 404 page; a failed read shows the screen's own error with a retry
// link. The screen is not in the main nav (AC6) and has no entry link on the subject page: nothing
// there is a natural place for it yet (the subject screen links to no sub-screen).
async function Graph({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ section?: string }>;
}) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  const { section } = await searchParams;
  let data: GraphData | null = null;
  try {
    data = await loadGraph(subject.id, section ?? null);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
  }
  if (data === null) {
    return (
      <PageColumn width="session">
        <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
          <p className="m-0 font-semibold">Không tải được đồ thị.</p>
          <a href={`/subjects/${subject.id}/graph`} className="mt-3 inline-flex min-h-11 items-center font-semibold rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
            Thử lại
          </a>
        </div>
      </PageColumn>
    );
  }
  return <GraphScreen live={{ subjectId: subject.id, subjectName: subject.name, data }} />;
}

export default function GraphPage(props: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ section?: string }>;
}) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="h-80 w-full rounded-sheet bg-sunken" />}>
        <Graph {...props} />
      </Suspense>
    </AppShell>
  );
}
