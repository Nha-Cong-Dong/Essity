import type { Metadata } from "next";

import { Mascot, type MascotPose } from "@/components/mascot";

export const metadata: Metadata = { title: "Design preview: mascot · Essity" };

// The four poses of Bé Trang side by side (phase B). Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts).
const POSES: MascotPose[] = ["vui", "cho", "chuanbi", "chucmung"];

export default function MascotFixture() {
  return (
    <main className="flex flex-wrap gap-8 p-8">
      {POSES.map((pose) => (
        <figure key={pose} className="m-0 flex flex-col items-center gap-2">
          <Mascot pose={pose} size="lg" />
          <figcaption className="text-meta">{pose}</figcaption>
        </figure>
      ))}
    </main>
  );
}
