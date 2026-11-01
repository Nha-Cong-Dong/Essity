import { withOrigin } from "@/lib/csrf";
import { readMerge } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02b AC8): merge cards (core-api does it without the AI).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = readMerge(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/sessions/{session_id}/drafts/merge", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
