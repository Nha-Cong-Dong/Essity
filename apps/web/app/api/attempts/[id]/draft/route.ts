import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { ANSWER, ANSWER_BODY_BYTES, forward } from "@/lib/review-routes";

// T2.9, T2.15: the answer box saves its text as a draft while the user types.
export const PUT = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, ANSWER, { maxBytes: ANSWER_BODY_BYTES });
  if (body === null) return errorResponse("invalid_request", 400);
  return forward(
    request,
    id,
    (core, attempt_id) =>
      core.PUT("/v1/attempts/{attempt_id}/draft", { params: { path: { attempt_id } }, body }),
    { route: "attempt", notFound: "attempt_not_found" },
  );
});
