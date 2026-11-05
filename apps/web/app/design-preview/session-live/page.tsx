import type { Metadata } from "next";
import { Suspense } from "react";

import { SessionLive } from "@/components/session-study/session-live";
import { DOCS, SUBJECT_NAME } from "@/lib/fixtures/session-study";
import { sectionParam } from "@/lib/session-study/entry";
import { initialRound } from "@/lib/session-study/round";

export const metadata: Metadata = { title: "Design preview: buổi học thật · Essity" };

// T7.12: the study session as the real page builds it (SessionLive on the browser's own calls to
// /api/...), with the documents fixed. The e2e answers those calls itself (page.route), so the main
// flow runs without core-api. Closed outside development unless WEB_DESIGN_PREVIEW=1.
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
// T7.12d: the subject whose cards by section the e2e answers (page.route).
const SUBJECT = "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f";

// T7.19 F2: `?section=` is a session opened from a suggestion (shows that section); none is free.
const FOR_SECTION = {
  kind: "section",
  text: "Nội dung học tập: 3.2 TCP flow control",
  reason: "Phần chưa học đầu tiên trong đề cương.",
  pace: "còn 12 phần, 20 ngày",
} as const;

async function Preview({ searchParams }: { searchParams: Promise<{ section?: string | string[] }> }) {
  const section = sectionParam((await searchParams).section);
  return (
    <SessionLive
      sessionId={SESSION}
      subjectId={SUBJECT}
      stayOnComplete
      subject={SUBJECT_NAME}
      stopHref="/design-preview"
      docs={DOCS}
      suggestion={section ? FOR_SECTION : undefined}
      sectionId={section ?? undefined}
      initial={{ round: initialRound, text: "", mentions: [], files: [] }}
    />
  );
}

export default function SessionLivePreview({ searchParams }: { searchParams: Promise<{ section?: string | string[] }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-screen bg-bg" />}>
      <Preview searchParams={searchParams} />
    </Suspense>
  );
}
