import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, unavailable } from "@/lib/http";
import { nextAfterBaseline } from "@/lib/onboarding";
import { SESSION_COOKIE } from "@/lib/session";

// T1.18, US-11 AC2: "Nhập sau". A POST, not a link: it records the skip, so core-api asks once
// more on a later visit and then never again (ADR-0014: no writes over GET).
export const POST = withOrigin(async (request) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);

  const core = coreClientFor(request, token);
  let result;
  try {
    result = await core.POST("/v1/baseline/skip");
  } catch (error) {
    return unavailable("baseline-skip", error);
  }
  const { response } = result;
  if (response.ok) return Response.json({ next: await nextAfterBaseline(core) });
  if (response.status === 401) return errorResponse("signed_out", 401);
  return unavailable("baseline-skip");
});
