import type { Metadata } from "next";

import { ReviewPreview } from "./preview";

export const metadata: Metadata = { title: "Design preview: ôn tập · Essity" };

// /review/[id] with fixed data, for the layout test (ADR-0025, T2.15): the real ReviewScreen, no
// core-api call and no session. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts,
// lib/design-preview.ts).
export default function ReviewLayoutFixture() {
  return <ReviewPreview />;
}
