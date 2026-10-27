import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forward } from "@/lib/review-routes";

// T2.19 (US-09 AC1): "Chấm sai" with its one choice; core-api answers the attempt with the new grade.
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
      core.POST("/v1/grades/{grade_id}/override", { params: { path: { grade_id } }, body: { verdict } }),
    { route: "attempt", notFound: "grade_not_found" },
  );
});
