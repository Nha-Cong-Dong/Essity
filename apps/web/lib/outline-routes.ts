import "server-only";

import type { NextRequest } from "next/server";

import { type CoreClient, coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T7.5 (US-01 AC5, US-13 AC4): web's routes for the outline. Each passes one core-api call (T7.4)
// on for the signed-in user and answers its JSON, or the code of its refusal. The browser's body is
// rebuilt field by field by the route, never forwarded.

// core-api's refusals the screen tells apart; anything else is "unavailable".
const CODES = new Set([
  "children_outside",
  "document_not_found",
  "document_not_ready",
  "invalid_range",
  "invalid_short_name",
  "nothing_to_change",
  "outside_document",
  "outside_parent",
  "section_not_found",
  "short_name_taken",
  "subject_not_found",
  "textbook_exists",
  "textbook_has_cards",
]);

type CoreResult = { data?: unknown; error?: unknown; response: Response };

/** Calls core-api for the signed-in user on `id` (a UUID, or 404 without a call). */
export async function forwardOutline(
  request: NextRequest,
  id: string,
  call: (core: CoreClient, id: string) => Promise<CoreResult>,
  notFound: string,
): Promise<Response> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  if (!isSubjectId(id)) return errorResponse(notFound, 404);
  let result: CoreResult;
  try {
    result = await call(coreClientFor(request, token), id);
  } catch (error) {
    return unavailable("documents", error);
  }
  const { data, error, response } = result;
  if (data !== undefined) return Response.json(data, { status: response.status });
  if (response.status === 401) return errorResponse("signed_out", 401);
  if (response.status === 429) return rateLimited(response);
  const body = error as { detail?: unknown; cards?: unknown } | undefined;
  if (typeof body?.detail === "string" && CODES.has(body.detail)) {
    // `textbook_has_cards` says how many cards the change would orphan: the confirmation shows it.
    if (body.detail === "textbook_has_cards" && typeof body.cards === "number") {
      return Response.json({ error: body.detail, cards: body.cards }, { status: response.status });
    }
    return errorResponse(body.detail, response.status);
  }
  if (response.status === 422) return errorResponse("invalid_request", 422);
  return unavailable("documents");
}
