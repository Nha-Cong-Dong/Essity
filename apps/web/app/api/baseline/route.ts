import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields, unavailable } from "@/lib/http";
import { nextAfterBaseline } from "@/lib/onboarding";
import { SESSION_COOKIE } from "@/lib/session";

// T1.18, US-11 AC1: "Lưu và tiếp tục" on /onboarding. GPA is personal data: it is never logged,
// and a 422 names the field without the value (ADR-0013).

const BASELINE = {
  gpa_before: { kind: "string" },
  prior_ready_days: { kind: "integer", optional: true },
  prior_days_unknown: { kind: "boolean" },
} as const;

const FIELDS = ["gpa_before", "prior_ready_days"] as const;

/** The fields a core-api 422 points at, by its `loc` (US-11 AC3). */
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

export const POST = withOrigin(async (request) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  const body = await readFields(request, BASELINE);
  if (body === null) return errorResponse("invalid_request", 400);

  const core = coreClientFor(request, token);
  let result;
  try {
    result = await core.POST("/v1/baseline", { body });
  } catch (error) {
    return unavailable("baseline", error);
  }
  const { response } = result;
  // 409: another tab saved it first. The baseline the user wanted is there (plan K4d).
  if (response.status === 201 || response.status === 409) {
    return Response.json({ next: await nextAfterBaseline(core) });
  }
  if (response.status === 401) return errorResponse("signed_out", 401);
  if (response.status === 422) {
    const detail = (result.error as { detail?: unknown } | undefined)?.detail;
    return Response.json({ error: "invalid", fields: invalidFields(detail) }, { status: 422 });
  }
  return unavailable("baseline");
});
