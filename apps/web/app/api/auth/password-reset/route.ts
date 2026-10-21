import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.14: "Quên mật khẩu". core-api answers the same for every address (AC5); so does this,
// even for one core-api finds malformed, so the form learns nothing about accounts.
export const POST = withOrigin(async (request) => {
  const body = await readStrings(request, ["email"]);
  if (body === null) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request).POST("/v1/auth/password-reset", { body });
  } catch (error) {
    return unavailable("password-reset", error);
  }
  const { response } = result;
  if (response.status === 202 || response.status === 422) return Response.json({ status: "sent" });
  if (response.status === 429) return rateLimited(response);
  return unavailable("password-reset");
});
