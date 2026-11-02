import { withOrigin } from "@/lib/csrf";
import { forward, GRADING_TIMEOUT_MS } from "@/lib/review-routes";

// T8.7: "Chấm lại" for a submitted practice answer with no grade yet.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, attempt_id) => core.POST("/v1/practice/attempts/{attempt_id}/regrade", { params: { path: { attempt_id } } }),
    { route: "attempt", notFound: "attempt_not_found", timeoutMs: GRADING_TIMEOUT_MS },
  );
});
