import type { Metadata } from "next";

import { SessionPreview } from "./preview";

export const metadata: Metadata = { title: "Design preview: buổi học · Essity" };

// The v2 study session (T7.12a) with fixed data and no core-api: a state switcher over its busiest
// states, for the layout test and for looking at. The live /subjects/[id]/sessions/new is not
// touched. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).
export default function SessionLayoutFixture() {
  return <SessionPreview />;
}
