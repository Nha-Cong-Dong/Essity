import "server-only";

import type { NextRequest } from "next/server";

import { coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";

// T9.3 (US-18): web's two routes for the command bar. Each passes one core-api call (T9.2e) on for
// the signed-in user and answers its JSON, or the stable code of its refusal. The browser's body is
// rebuilt field by field by the route, never forwarded; the text of a command is never logged.

// core waits up to 8 s on the parser (ADR-0030); web waits a little longer than that.
export const COMMAND_TIMEOUT_MS = 12_000;

// core-api's refusals the bar tells apart; any other string detail of a 4xx is "rejected".
const CODES = new Set([
  "ai_disabled",
  "changed_after",
  "command_id_reused",
  "conflict",
  "email_not_verified",
  "empty_command",
  "id_collision",
  "not_latest",
  "not_owned",
  "nothing_to_undo",
  "other_session",
  "parse_invalid",
  "parse_unavailable",
  "quota_hard_cap",
  "subject_not_found",
  "unitchangedelsewhere",
  "unsupported",
]);

type CoreResult = { data?: unknown; error?: unknown; response: Response };
type CoreClient = ReturnType<typeof coreClientFor>;

export async function forwardCommand(
  request: NextRequest,
  call: (core: CoreClient) => Promise<CoreResult>,
): Promise<Response> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  let result: CoreResult;
  try {
    result = await call(coreClientFor(request, token, COMMAND_TIMEOUT_MS));
  } catch (error) {
    return unavailable("commands", error);
  }
  const { data, error, response } = result;
  if (data !== undefined) return Response.json(data, { status: response.status });
  if (response.status === 401) return errorResponse("signed_out", 401);
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  // The AI budget is spent (AC8): the bar turns itself off. Any other 429 is the rate limit.
  if (response.status === 429) {
    return detail === "quota_hard_cap" ? errorResponse("quota_hard_cap", 429) : rateLimited(response);
  }
  if (typeof detail === "string" && response.status < 500) {
    return errorResponse(CODES.has(detail) ? detail : "rejected", response.status);
  }
  if (response.status === 422) return errorResponse("invalid_request", 422);
  if (response.status === 502 || response.status === 503) {
    return errorResponse(typeof detail === "string" && CODES.has(detail) ? detail : "unavailable", response.status);
  }
  return unavailable("commands");
}
