import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { requireVerifiedSession } from "@/lib/session";

// Q23: the old per-subject graph route. The graph of every subject lives at /graph; this link
// (still on the Today screen) opens it with this subject switched on and the others off.
async function Go({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const { id } = await params;
  return redirect(`/graph?subject=${encodeURIComponent(id)}`);
}

export default function SubjectGraphRedirect(props: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={null}>
      <Go {...props} />
    </Suspense>
  );
}
