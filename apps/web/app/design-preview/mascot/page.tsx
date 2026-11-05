import type { Metadata } from "next";

import { Mascot, type MascotPose } from "@/components/mascot";

export const metadata: Metadata = { title: "Design preview: mascot · Essity" };

// The five poses and the glyph of the v4 mascot side by side, on the page and on the field (DESIGN-V4). Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).
const POSES: MascotPose[] = ["chao", "khen", "nghi", "cho", "rong", "glyph"];

export default function MascotFixture() {
  return (
    <main className="flex flex-wrap gap-8 p-8">
      {POSES.map((pose) => (
        <figure key={pose} className="m-0 flex flex-col items-center gap-2">
          <Mascot pose={pose} size="lg" />
          <div className="rounded-tile bg-field p-3">
            <Mascot pose={pose} size="md" tone="solid" />
          </div>
          <figcaption className="text-meta">{pose}</figcaption>
        </figure>
      ))}
    </main>
  );
}
