import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { ANSWER, ANSWER_BODY_BYTES, forward, GRADING_TIMEOUT_MS } from "@/lib/review-routes";

// T2.13: "Nộp" saves the last text, submits it and has it graded at once. A grading that fails
// still answers 200: the answer is kept and the screen offers "Chấm lại".
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, ANSWER, { maxBytes: ANSWER_BODY_BYTES });
  if (body === null) return errorResponse("invalid_request", 400);
  return forward(
    request,
    id,
    (core, attempt_id) =>
      core.POST("/v1/attempts/{attempt_id}/submit", { params: { path: { attempt_id } }, body }),
    { route: "attempt", notFound: "attempt_not_found", timeoutMs: GRADING_TIMEOUT_MS },
  );
});
