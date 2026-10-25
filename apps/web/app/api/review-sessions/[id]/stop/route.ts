import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// US-08, plan D-8: "Dừng tại đây" and the last question close the session, then go to /today.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/review-sessions/{session_id}/stop", { params: { path: { session_id } } }),
    { route: "review-sessions", notFound: "session_not_found" },
  );
});
