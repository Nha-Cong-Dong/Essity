import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// T2.9, T2.15: open the current question's attempt (its draft), or the one already open.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/review-sessions/{session_id}/attempts", { params: { path: { session_id } } }),
    { route: "review-sessions", notFound: "session_not_found" },
  );
});
