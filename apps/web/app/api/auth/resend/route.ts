import { pendingEmail, sessionUser } from "@/lib/account";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";

// T1.13, AC2: "Gửi lại" on /check-email. The address comes from the session or the sign-up
// cookie, never from the request body, so this cannot mail anyone else.
export const POST = withOrigin(async (request) => {
  let result;
  try {
    const email = (await sessionUser(request))?.email ?? pendingEmail(request);
    if (email === null) return errorResponse("no_email", 400);
    result = await coreClientFor(request).POST("/v1/auth/verify-email/resend", { body: { email } });
  } catch (error) {
    return unavailable("resend", error);
  }
  const { response } = result;
  if (response.status === 202) return Response.json({ status: "sent" });
  if (response.status === 429) return rateLimited(response);
  return unavailable("resend");
});
