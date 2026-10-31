import type { NextRequest } from "next/server";

import { forwardOutline } from "@/lib/outline-routes";

type Params = { params: Promise<{ id: string }> };

// T7.5 (US-13): the outline of the subject's main textbook (a GET: no origin check). The screen
// polls it while the textbook is still being read.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardOutline(
    request,
    id,
    (core, subject_id) => core.GET("/v1/subjects/{subject_id}/outline", { params: { path: { subject_id } } }),
    "subject_not_found",
  );
}
