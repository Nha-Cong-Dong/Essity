import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { requireVerifiedSession } from "@/lib/session";
import { StartStudy } from "@/components/session-study/start-study";

export const metadata: Metadata = { title: "Buổi học · Essity" };

// The session check stays in the page (source-rules: every private page asks core-api).
async function Guarded({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  return <StartStudy params={params} />;
}

export default function NewStudySession({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Guarded params={params} />
    </Suspense>
  );
}
