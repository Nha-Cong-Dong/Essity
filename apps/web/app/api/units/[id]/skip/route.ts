import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forward } from "@/lib/review-routes";
import { isSubjectId } from "@/lib/subject-id";

type Params = { params: Promise<{ id: string }> };

// T2.24 (US-04 AC5): "Không cần ôn phần này". The answer holds the next question of the session.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readFields(request, { review_session_id: { kind: "string", optional: true } } as const, {
    maxBytes: 256,
  });
  if (body === null || (body.review_session_id !== undefined && !isSubjectId(body.review_session_id))) {
    return errorResponse("invalid_request", 400);
  }
  const review_session_id = body.review_session_id;
  return forward(
    request,
    id,
    (core, unit_id) =>
      core.POST("/v1/units/{unit_id}/skip", { params: { path: { unit_id } }, body: { review_session_id } }),
    { route: "review-sessions", notFound: "unit_not_found" },
  );
});

// "Hoàn tác" right after: 204 whether or not the unit was skipped.
export const DELETE = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const session = new URL(request.url).searchParams.get("review_session_id") ?? undefined;
  if (session !== undefined && !isSubjectId(session)) return errorResponse("invalid_request", 400);
  return forward(
    request,
    id,
    (core, unit_id) =>
      core.DELETE("/v1/units/{unit_id}/skip", {
        params: { path: { unit_id }, query: { review_session_id: session } },
      }),
    { route: "review-sessions", notFound: "unit_not_found" },
  );
});
