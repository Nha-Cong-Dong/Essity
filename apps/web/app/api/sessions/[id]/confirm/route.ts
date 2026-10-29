import { withOrigin } from "@/lib/csrf";
import { errorResponse } from "@/lib/http";
import { forwardSession, readConfirm } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T4.13a (US-02 AC4, AC7): "Lưu". The card as the learner left it; core-api writes the session.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = readConfirm(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/sessions/{session_id}/confirm", {
        params: { path: { session_id } },
        body,
      }),
    { notFound: "session_not_found" },
  );
});
