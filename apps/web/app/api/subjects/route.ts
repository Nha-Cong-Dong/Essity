import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { subjectError } from "@/lib/subject-errors";

// T1.20, US-01 AC1: "Tạo môn" with exactly a name and an exam date (ISO, from the form).
const NEW_SUBJECT = { name: { kind: "string" }, exam_date: { kind: "string" } } as const;

export const POST = withOrigin(async (request) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  const body = await readFields(request, NEW_SUBJECT);
  if (body === null) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request, token).POST("/v1/subjects", { body });
  } catch (error) {
    return unavailable("subjects", error);
  }
  if (result.data) return Response.json({ id: result.data.id }, { status: 201 });
  return subjectError("subjects", result.response, result.error);
});
