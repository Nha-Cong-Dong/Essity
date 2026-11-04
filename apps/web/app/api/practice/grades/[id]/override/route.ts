import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forward } from "@/lib/review-routes";

// REVIEW-SEED: "Chấm sai" on a practice result; core-api answers the attempt with the new grade and
// rebuilds the question's schedule from the last attempt's latest grade.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, { verdict: { kind: "string" } } as const, { maxBytes: 256 });
  if (body === null || (body.verdict !== "correct" && body.verdict !== "incorrect")) {
    return errorResponse("invalid_request", 400);
  }
  const verdict = body.verdict;
  return forward(
    request,
    id,
    (core, grade_id) =>
      core.POST("/v1/practice/grades/{grade_id}/override", { params: { path: { grade_id } }, body: { verdict } }),
    { route: "attempt", notFound: "grade_not_found" },
  );
});
