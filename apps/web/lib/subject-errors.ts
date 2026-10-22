import { errorResponse, unavailable } from "@/lib/http";
import type { LogRoute } from "@/lib/log";

// How web's /api/subjects routes pass on core-api's refusals (T1.20). The 422 names the field,
// never the value typed (ADR-0013: a subject name is the user's own text).

const FIELDS = ["name", "exam_date"] as const;

function invalidFields(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  const named = new Set(
    detail.flatMap((error) => {
      const loc: unknown = (error as { loc?: unknown } | null)?.loc;
      return Array.isArray(loc) ? FIELDS.filter((field) => loc.includes(field)) : [];
    }),
  );
  return FIELDS.filter((field) => named.has(field));
}

/** core-api's answer that is not a success, as web's error. */
export function subjectError(route: LogRoute, response: Response, error: unknown): Response {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (response.status === 401) return errorResponse("signed_out", 401);
  if (response.status === 404) return errorResponse("subject_not_found", 404);
  if (response.status === 422) {
    // US-01 AC2, plan K17: a business refusal is a string code (plan B20).
    if (detail === "exam_date_not_in_future" || detail === "exam_date_too_far") {
      return errorResponse(detail, 422);
    }
    return Response.json({ error: "invalid", fields: invalidFields(detail) }, { status: 422 });
  }
  return unavailable(route);
}
