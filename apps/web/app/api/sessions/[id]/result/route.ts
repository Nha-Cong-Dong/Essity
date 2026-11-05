import type { NextRequest } from "next/server";

import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// CARDS-V3: where a handed-in session stands (submission status, its title, how many cards went
// into the Kho). Read each time, so leaving the screen and coming back shows the true state.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, session_id) => core.GET("/v1/vault/sessions/{session_id}/result", { params: { path: { session_id } } }),
    { notFound: "session_not_found" },
  );
}
