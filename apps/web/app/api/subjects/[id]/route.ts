import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { subjectError } from "@/lib/subject-errors";
import { isSubjectId } from "@/lib/subject-id";

// T1.20, plan K2: "Sửa" on /subjects changes the name, the exam date or both.
const CHANGE = {
  name: { kind: "string", optional: true },
  exam_date: { kind: "string", optional: true },
} as const;

export const PATCH = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  // Only a UUID goes into core-api's path: ".." would reach another endpoint (review plan R1).
  const { id } = await params;
  if (!isSubjectId(id)) return errorResponse("subject_not_found", 404);
  const body = await readFields(request, CHANGE);
  if (body === null || Object.keys(body).length === 0) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request, token).PATCH("/v1/subjects/{subject_id}", {
      params: { path: { subject_id: id } },
      body,
    });
  } catch (error) {
    return unavailable("subject", error);
  }
  const { data } = result;
  if (data) {
    const { name, exam_date, days_until_exam } = data;
    return Response.json({ subject: { id: data.id, name, exam_date, days_until_exam } });
  }
  return subjectError("subject", result.response, result.error);
});

// T2.3b, us-01 AC8: delete a subject with no review history. core-api answers 204 with no body,
// so success is read from the status, not from `data`.
export const DELETE = withOrigin(
  async (request, { params }: { params: Promise<{ id: string }> }) => {
    const token = request.cookies.get(SESSION_COOKIE)?.value;
    if (!token) return errorResponse("signed_out", 401);
    const { id } = await params;
    if (!isSubjectId(id)) return errorResponse("subject_not_found", 404);

    let result;
    try {
      result = await coreClientFor(request, token).DELETE("/v1/subjects/{subject_id}", {
        params: { path: { subject_id: id } },
      });
    } catch (error) {
      return unavailable("subject", error);
    }
    if (result.response.status === 204) return new Response(null, { status: 204 });
    return subjectError("subject", result.response, result.error);
  },
);
