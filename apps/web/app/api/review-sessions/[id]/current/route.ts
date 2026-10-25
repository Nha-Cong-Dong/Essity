import type { NextRequest } from "next/server";

import { forward } from "@/lib/review-routes";

type Params = { params: Promise<{ id: string }> };

// T2.15: the session's current question, or done (with the answers left ungraded, plan D-7).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, session_id) =>
      core.GET("/v1/review-sessions/{session_id}/current", { params: { path: { session_id } } }),
    { route: "review-sessions", notFound: "session_not_found" },
  );
}
