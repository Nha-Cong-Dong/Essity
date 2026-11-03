import { coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { checkUsernameAvailable } from "@/lib/username-available";
import { usernameProblem } from "@/lib/username";

// T1.24: the sign-up form asks, on blur, whether a username is free (D2: a username is not a
// secret, core-api rate-limits it per IP). Only a well-formed name is passed on.
export async function GET(request: Request) {
  const username = new URL(request.url).searchParams.get("username") ?? "";
  if (usernameProblem(username) !== null) return errorResponse("invalid_request", 400);
  let result;
  try {
    result = await checkUsernameAvailable(coreClientFor(request), username);
  } catch (error) {
    return unavailable("register", error);
  }
  if (result instanceof Response) {
    return result.status === 429 ? rateLimited(result) : unavailable("register");
  }
  return Response.json(result);
}
