import { coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { usernameProblem } from "@/lib/username";

// T1.24: the sign-up form asks, on blur, whether a username is free (D2: a username is not a
// secret, core-api rate-limits it per IP). Only a well-formed name is passed on.
export async function GET(request: Request) {
  const username = new URL(request.url).searchParams.get("username") ?? "";
  if (usernameProblem(username) !== null) return errorResponse("invalid_request", 400);
  let result;
  try {
    result = await coreClientFor(request).GET("/v1/auth/username-availability", { params: { query: { u: username } } });
  } catch (error) {
    return unavailable("register", error);
  }
  const { data, response } = result;
  if (data) return Response.json({ available: data.available, reason: data.reason });
  if (response.status === 429) return rateLimited(response);
  return unavailable("register");
}
