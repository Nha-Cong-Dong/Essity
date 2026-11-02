import type { Metadata } from "next";
import { Suspense } from "react";

import { StartStudy } from "@/components/session-study/start-study";

export const metadata: Metadata = { title: "Buổi học · Essity" };

export default function NewStudySession({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <StartStudy params={params} />
    </Suspense>
  );
}
