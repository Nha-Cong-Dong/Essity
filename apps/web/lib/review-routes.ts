import "server-only";

import type { NextRequest } from "next/server";

import { type CoreClient, coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import type { LogRoute } from "@/lib/log";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T2.15, T2.13: what the answer screen's routes share. Each passes one call on to core-api and
// answers core-api's JSON, or the code of its refusal.

/** The body of a draft save or a submit (core-api's AnswerIn). */
export const ANSWER = {
  answer_text: { kind: "string" },
  dont_remember: { kind: "boolean" },
} as const;

/** 4000 characters of up to 4 bytes each, with room for JSON escapes (plan 🟡15). */
export const ANSWER_BODY_BYTES = 32 * 1024;

/** Submitting and "Chấm lại" wait on the AI: up to 20 s in core-api, then the write (plan D-5). */
export const GRADING_TIMEOUT_MS = 25_000;

// core-api's refusals the screen tells apart; anything else is "unavailable".
const CODES = new Set([
  "answer_empty",
  "attempt_not_found",
  "attempt_not_submitted",
  "attempt_submitted",
  "grade_not_found",
  "grade_not_current",
  "grading_in_progress",
  "question_not_found",
  "session_done",
  "session_ended",
  "session_not_found",
  "subject_deleted",
]);

type CoreResult = { data?: unknown; error?: unknown; response: Response };

type Options = { route: LogRoute; notFound: string; timeoutMs?: number };

/**
 * Calls core-api for the signed-in user on the attempt or session `id`. Only a UUID goes into
 * core-api's path (review plan R1); any other id is `notFound` without a call.
 */
export async function forward(
  request: NextRequest,
  id: string,
  call: (core: CoreClient, id: string) => Promise<CoreResult>,
  { route, notFound, timeoutMs }: Options,
): Promise<Response> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  if (!isSubjectId(id)) return errorResponse(notFound, 404);
  let result: CoreResult;
  try {
    result = await call(coreClientFor(request, token, timeoutMs), id);
  } catch (error) {
    return unavailable(route, error);
  }
  const { data, error, response } = result;
  if (data !== undefined) return Response.json(data, { status: response.status });
  if (response.status === 204) return new Response(null, { status: 204 }); // a draft saved

  if (response.status === 401) return errorResponse("signed_out", 401);
  if (response.status === 429) return rateLimited(response);
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && CODES.has(detail)) return errorResponse(detail, response.status);
  // A list of field errors: the text is too long or holds a character core-api refuses.
  if (response.status === 422) return errorResponse("invalid_answer", 422);
  return unavailable(route);
}
