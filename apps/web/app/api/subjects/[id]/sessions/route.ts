import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { CARD_TIMEOUT_MS, forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T4.13a (US-02 AC1): the sentence goes to core-api, which answers the card to confirm. 2000
// characters of up to 4 bytes each, with room for JSON escapes.
const DESCRIBE = { description: { kind: "string" } } as const;

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readFields(request, DESCRIBE, { maxBytes: 32 * 1024 });
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, subject_id) =>
      core.POST("/v1/subjects/{subject_id}/sessions", { params: { path: { subject_id } }, body }),
    { notFound: "subject_not_found", timeoutMs: CARD_TIMEOUT_MS },
  );
});
