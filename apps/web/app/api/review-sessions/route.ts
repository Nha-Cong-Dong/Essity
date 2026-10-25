import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T2.14: "Bắt đầu" / "Tiếp tục" on /today. core-api makes today's session or returns the one
// still open (T2.9 plan C4); the browser only needs its id to go to /review/{id}.
const START = { subject_id: { kind: "string", optional: true } } as const;

export const POST = withOrigin(async (request) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  const body = await readFields(request, START);
  if (body === null) return errorResponse("invalid_request", 400);
  if (body.subject_id !== undefined && !isSubjectId(body.subject_id)) {
    return errorResponse("invalid_request", 400);
  }

  let result;
  try {
    result = await coreClientFor(request, token).POST("/v1/review-sessions", { body });
  } catch (error) {
    return unavailable("review-sessions", error);
  }
  if (result.data) return Response.json({ id: result.data.id });
  const detail = (result.error as { detail?: unknown } | undefined)?.detail;
  if (result.response.status === 401) return errorResponse("signed_out", 401);
  if (result.response.status === 404) return errorResponse("subject_not_found", 404);
  if (result.response.status === 409 && detail === "nothing_to_review") {
    return errorResponse("nothing_to_review", 409);
  }
  return unavailable("review-sessions");
});
