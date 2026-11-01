import { withOrigin } from "@/lib/csrf";
import { readSplit } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02b AC8): split a card into parts the learner wrote, with `If-Match`.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const split = readSplit(await request.json().catch(() => null));
  if (split === null) return errorResponse("invalid_request", 400);
  const { version, parts } = split;
  return forwardSession(
    request,
    id,
    (core, unit_id) =>
      core.POST("/v1/drafts/{unit_id}/split", {
        params: { path: { unit_id }, header: { "if-match": String(version) } },
        body: { parts },
      }),
    { notFound: "unit_not_found" },
  );
});
