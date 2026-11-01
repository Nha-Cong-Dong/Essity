import type { Metadata } from "next";

import { SessionLive } from "@/components/session-study/session-live";
import { DOCS, SUBJECT_NAME } from "@/lib/fixtures/session-study";
import { initialRound } from "@/lib/session-study/round";

export const metadata: Metadata = { title: "Design preview: buổi học thật · Essity" };

// T7.12: the study session as the real page builds it (SessionLive on the browser's own calls to
// /api/...), with the documents fixed. The e2e answers those calls itself (page.route), so the main
// flow runs without core-api. Closed outside development unless WEB_DESIGN_PREVIEW=1.
const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";

export default function SessionLivePreview() {
  return (
    <SessionLive
      sessionId={SESSION}
      subject={SUBJECT_NAME}
      stopHref="/design-preview"
      docs={DOCS}
      initial={{ round: initialRound, drafts: [], text: "", mentions: [], files: [], scope: [], saved: "free", resumed: false }}
    />
  );
}
