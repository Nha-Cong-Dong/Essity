import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { ANSWER, ANSWER_BODY_BYTES, forward } from "@/lib/review-routes";

// T8.7 (US-16 AC2, US-04 AC3): the practice answer box saves its text while the user types.
export const PUT = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, ANSWER, { maxBytes: ANSWER_BODY_BYTES });
  if (body === null) return errorResponse("invalid_request", 400);
  return forward(
    request,
    id,
    (core, attempt_id) => core.PUT("/v1/practice/attempts/{attempt_id}/draft", { params: { path: { attempt_id } }, body }),
    { route: "attempt", notFound: "attempt_not_found" },
  );
});
