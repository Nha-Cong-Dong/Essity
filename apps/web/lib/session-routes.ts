import "server-only";

import type { NextRequest } from "next/server";

import { type CoreClient, coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T4.13a (US-02): web's routes for logging a study session. Each passes one call on to core-api
// (T4.12) and answers its JSON, or the code of its refusal. What the user wrote is never logged.

/** web -> core-api for the card: core-api's own budget is 4.5 s, plus the hop (T4.12 hand-off). */
export const CARD_TIMEOUT_MS = 6000;

// core-api's refusals the screen tells apart; anything else is "unavailable".
const CODES = new Set([
  "bad_date",
  "bad_range",
  "document_not_found",
  "not_indexed",
  "session_not_found",
  "subject_not_found",
]);

type CoreResult = { data?: unknown; error?: unknown; response: Response };

/** Calls core-api for the signed-in user on `id` (a UUID, or `notFound` without a call). */
export async function forwardSession(
  request: NextRequest,
  id: string,
  call: (core: CoreClient, id: string) => Promise<CoreResult>,
  { notFound, timeoutMs }: { notFound: string; timeoutMs?: number },
): Promise<Response> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  if (!isSubjectId(id)) return errorResponse(notFound, 404);
  let result: CoreResult;
  try {
    result = await call(coreClientFor(request, token, timeoutMs), id);
  } catch (error) {
    return unavailable("sessions", error);
  }
  const { data, error, response } = result;
  if (data !== undefined) return Response.json(data, { status: response.status });
  if (response.status === 401) return errorResponse("signed_out", 401);
  if (response.status === 429) return rateLimited(response);
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && CODES.has(detail)) return errorResponse(detail, response.status);
  if (response.status === 422) return errorResponse("invalid_request", 422);
  return unavailable("sessions");
}

const DEPTHS = new Set(["deep", "skim", "unclear"]);

type Range = {
  document_id: string;
  start_page: number;
  end_page: number;
  depth: "deep" | "skim" | "unclear";
  start_label?: string;
  end_label?: string;
};
export type ConfirmBody = { ranges: Range[]; studied_on?: string };

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function readRange(value: unknown): Range | null {
  if (!isObject(value)) return null;
  const { document_id, start_page, end_page, depth, start_label, end_label } = value;
  if (typeof document_id !== "string" || !isSubjectId(document_id)) return null;
  if (!Number.isSafeInteger(start_page) || !Number.isSafeInteger(end_page)) return null;
  if (typeof depth !== "string" || !DEPTHS.has(depth)) return null;
  for (const label of [start_label, end_label]) {
    if (label !== undefined && label !== null && typeof label !== "string") return null;
  }
  const range: Range = {
    document_id,
    start_page: start_page as number,
    end_page: end_page as number,
    depth: depth as Range["depth"],
  };
  if (typeof start_label === "string") range.start_label = start_label;
  if (typeof end_label === "string") range.end_label = end_label;
  return range;
}

/**
 * The confirm body, rebuilt field by field (review plan R1). Notes wait for T4.13b: a body that
 * carries any is refused, so nothing unchecked reaches core-api.
 */
export function readConfirm(body: unknown): ConfirmBody | null {
  if (!isObject(body)) return null;
  if (!Object.keys(body).every((key) => key === "ranges" || key === "studied_on")) return null;
  if (!Array.isArray(body.ranges) || body.ranges.length > 6) return null;
  const ranges: Range[] = [];
  for (const item of body.ranges) {
    const range = readRange(item);
    if (range === null) return null;
    ranges.push(range);
  }
  if (body.studied_on === undefined) return { ranges };
  if (typeof body.studied_on !== "string") return null;
  return { ranges, studied_on: body.studied_on };
}
