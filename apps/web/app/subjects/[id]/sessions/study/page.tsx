import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { requireVerifiedSession } from "@/lib/session";
import { sectionParam } from "@/lib/session-study/entry";
import { StartStudy } from "@/components/session-study/start-study";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ section?: string | string[] }> };

export const metadata: Metadata = { title: "Buổi học · Essity" };

// The session check stays in the page (source-rules: every private page asks core-api).
async function Guarded({ params, searchParams }: Props) {
  await connection();
  await requireVerifiedSession();
  return <StartStudy params={params} section={sectionParam((await searchParams).section)} />;
}

export default function NewStudySession({ params, searchParams }: Props) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Guarded params={params} searchParams={searchParams} />
    </Suspense>
  );
}
