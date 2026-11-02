import { withOrigin } from "@/lib/csrf";
import { readSubmit } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

// T7.12 (US-02 AC2-AC4): hand in the learner's sentence and its @ mentions. Core-api resolves the
// mentions; a refusal comes back as its code and the index of the mention (never the text).
export const POST = withOrigin(async (request) => {
  const body = readSubmit(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(request, body.session_id, (core) => core.POST("/v1/submissions", { body: body }), {
    notFound: "session_not_found",
  });
});
