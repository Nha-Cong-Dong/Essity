import type { Metadata } from "next";
import { Suspense } from "react";

import { EndPreview } from "./preview";

export const metadata: Metadata = { title: "Design preview: kết thúc buổi học · Essity" };

// V4-SCREENS-B: the pop-up after "Kết thúc buổi học", open on a plain page (`?empty=1` for a session
// with nothing written). Its buttons do nothing here. Closed outside development unless WEB_DESIGN_PREVIEW=1.
async function Preview({ searchParams }: { searchParams: Promise<{ empty?: string }> }) {
  const { empty } = await searchParams;
  return (
    <main className="min-h-screen bg-bg p-8">
      <h1 className="m-0 font-display text-title">Buổi học: Xác suất thống kê</h1>
      <EndPreview empty={empty === "1"} />
    </main>
  );
}

export default function SessionEndPreview(props: { searchParams: Promise<{ empty?: string }> }) {
  return (
    <Suspense fallback={null}>
      <Preview {...props} />
    </Suspense>
  );
}
