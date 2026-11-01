import type { NextRequest } from "next/server";

import { withOrigin } from "@/lib/csrf";
import { readAdd } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02b AC6): the cards of a session and where the submission stands, read each time so
// leaving the screen and coming back shows the true state; and a card added by hand.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, session_id) => core.GET("/v1/sessions/{session_id}/drafts", { params: { path: { session_id } } }),
    { notFound: "session_not_found" },
  );
}

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readAdd(request);
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) => core.POST("/v1/sessions/{session_id}/drafts", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
