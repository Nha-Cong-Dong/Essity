import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { SourceView } from "@/components/card-source/source-view";
import { AppShell, PageColumn } from "@/components/shells";
import type { CardSources } from "@/lib/card-source";
import { loadCardSources } from "@/lib/card-source-load";
import { requireVerifiedSession } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";

export const metadata: Metadata = { title: "Nguồn của thẻ · Essity" };

// G4: the source of one card: the page (or note) it came from, the cited passage highlighted.
async function Source({ params }: { params: Promise<{ cardId: string }> }) {
  await connection();
  await requireVerifiedSession();
  const { cardId } = await params;
  let data: CardSources | null = null;
  try {
    data = await loadCardSources(cardId);
  } catch (error) {
    if (error instanceof CoreStatusError) {
      if (error.status === 401) redirect("/login");
      if (error.status === 404) notFound();
    }
  }
  if (data === null) {
    return (
      <PageColumn width="read">
        <p role="alert" className="m-0 font-semibold">
          Không tải được nguồn của thẻ.
        </p>
      </PageColumn>
    );
  }
  return (
    <PageColumn width="read">
      <a href="/today" className="inline-flex min-h-11 items-center text-meta underline">
        Về hôm nay
      </a>
      <h1 className="mt-2 mb-4">{data.title}</h1>
      {data.sources.length === 0 ? (
        <p className="m-0 text-ink-soft">Thẻ này chưa có nguồn nào.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {data.sources.map((s) => (
            <SourceView key={s.anchor_id} source={s} />
          ))}
        </div>
      )}
    </PageColumn>
  );
}

export default function CardSourcePage(props: { params: Promise<{ cardId: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<div aria-busy="true" className="h-80 w-full rounded-sheet bg-sunken" />}>
        <Source {...props} />
      </Suspense>
    </AppShell>
  );
}
