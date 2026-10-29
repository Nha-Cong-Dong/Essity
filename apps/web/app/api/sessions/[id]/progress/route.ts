import type { NextRequest } from "next/server";

import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T4.18 (US-02 AC11): where processing the saved session stands, read from core-api each time
// (never kept here), so leaving the page and coming back shows the true state.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, session_id) => core.GET("/v1/sessions/{session_id}/progress", { params: { path: { session_id } } }),
    { notFound: "session_not_found" },
  );
}
