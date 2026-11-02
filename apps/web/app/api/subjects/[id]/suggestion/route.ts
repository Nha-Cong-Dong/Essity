import type { NextRequest } from "next/server";

import { forwardOutline } from "@/lib/outline-routes";

type Params = { params: Promise<{ id: string }> };

// T7.13 (US-15 AC6): "Gợi ý cho hôm nay" on the subject screen. A GET: no origin check, nothing
// is written (the session a suggestion opens is recorded when it is saved).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardOutline(
    request,
    id,
    (core, subject_id) => core.GET("/v1/subjects/{subject_id}/suggestion", { params: { path: { subject_id } } }),
    "subject_not_found",
  );
}
