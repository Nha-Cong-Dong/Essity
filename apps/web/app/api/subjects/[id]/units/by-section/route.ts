import type { NextRequest } from "next/server";

import { forwardOutline } from "@/lib/outline-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12d (US-02b AC14): the subject's draft and canonical cards grouped by outline section (a GET:
// no origin check).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardOutline(
    request,
    id,
    (core, subject_id) => core.GET("/v1/subjects/{subject_id}/units/by-section", { params: { path: { subject_id } } }),
    "subject_not_found",
  );
}
