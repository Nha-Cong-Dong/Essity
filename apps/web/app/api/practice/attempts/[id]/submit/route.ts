import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { ANSWER, ANSWER_BODY_BYTES, forward, GRADING_TIMEOUT_MS } from "@/lib/review-routes";

// T8.7 (US-16 AC2, AC5): submit and grade at once. `hidden_ms` is the time the tab was hidden; the
// server subtracts it from its own (submit - served) clock. A failed grading still answers 200.
const BODY = { ...ANSWER, hidden_ms: { kind: "integer" } } as const;

export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, BODY, { maxBytes: ANSWER_BODY_BYTES });
  if (body === null || body.hidden_ms < 0) return errorResponse("invalid_request", 400);
  return forward(
    request,
    id,
    (core, attempt_id) => core.POST("/v1/practice/attempts/{attempt_id}/submit", { params: { path: { attempt_id } }, body }),
    { route: "attempt", notFound: "attempt_not_found", timeoutMs: GRADING_TIMEOUT_MS },
  );
});
