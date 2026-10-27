import { withOrigin } from "@/lib/csrf";
import { forward, GRADING_TIMEOUT_MS } from "@/lib/review-routes";

// T2.13: "Chấm lại" grades a submitted answer that has no grade yet; a graded one comes back as
// it is, never paid for twice.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, attempt_id) =>
      core.POST("/v1/attempts/{attempt_id}/regrade", { params: { path: { attempt_id } } }),
    { route: "attempt", notFound: "attempt_not_found", timeoutMs: GRADING_TIMEOUT_MS },
  );
});
