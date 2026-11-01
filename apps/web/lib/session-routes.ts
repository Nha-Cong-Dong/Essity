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
  "bad_note",
  "bad_range",
  "bad_split",
  "content_mismatch",
  "document_not_found",
  "file_too_large",
  "mention_ambiguous",
  "mention_not_found",
  "merge_needs_two",
  "nothing_submitted",
  "not_a_draft",
  "not_undoable",
  "scope_ambiguous",
  "scope_not_found",
  "scope_out_of_range",
  "scope_unsupported",
  "text_too_long",
  "too_many_mentions",
  "undo_expired",
  "unit_changed_elsewhere",
  "unit_not_found",
  "not_indexed",
  "session_confirmed",
  "session_not_found",
  "size_mismatch",
  "storage_quota_exceeded",
  "storage_unavailable",
  "subject_not_found",
  "too_many_notes",
  "upload_incomplete",
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
  // T7.12: T7.6 and T7.8 refuse with an object `{code, ...}`; only the code and the index of the
  // mention (the part of the text, `part`, is never passed on) reach the browser.
  if (typeof detail === "object" && detail !== null) {
    const { code, mention } = detail as { code?: unknown; mention?: unknown };
    if (typeof code === "string" && CODES.has(code)) {
      const found = Number.isSafeInteger(mention) ? { mention } : {};
      return Response.json({ error: code, ...found }, { status: response.status });
    }
  }
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
const NOTE_MIMES = ["image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"] as const;
type NoteMime = (typeof NOTE_MIMES)[number];
type Note = { sha256: string; mime: NoteMime; size_bytes: number };
const MAX_NOTES = 20;
export type ConfirmBody = { ranges: Range[]; notes: Note[]; studied_on?: string };

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

/** One note as core-api takes it (a hash, a type from the list, a size), rebuilt; else null. */
export function readNote(value: unknown): Note | null {
  if (!isObject(value)) return null;
  if (!Object.keys(value).every((key) => key === "sha256" || key === "mime" || key === "size_bytes")) return null;
  const { sha256, mime, size_bytes } = value;
  if (typeof sha256 !== "string" || !/^[0-9a-f]{64}$/.test(sha256)) return null;
  if (typeof mime !== "string" || !(NOTE_MIMES as readonly string[]).includes(mime)) return null;
  if (!Number.isSafeInteger(size_bytes) || (size_bytes as number) <= 0) return null;
  return { sha256, mime: mime as NoteMime, size_bytes: size_bytes as number };
}

/**
 * The confirm body, rebuilt field by field (review plan R1): ranges, notes and the day, nothing
 * else. A note reaches core-api only as a hash, a type and a size, which it checks against what
 * is stored.
 */
export function readConfirm(body: unknown): ConfirmBody | null {
  if (!isObject(body)) return null;
  if (!Object.keys(body).every((key) => key === "ranges" || key === "notes" || key === "studied_on")) return null;
  if (!Array.isArray(body.ranges) || body.ranges.length > 6) return null;
  const ranges: Range[] = [];
  for (const item of body.ranges) {
    const range = readRange(item);
    if (range === null) return null;
    ranges.push(range);
  }
  const notes: Note[] = [];
  if (body.notes !== undefined) {
    if (!Array.isArray(body.notes) || body.notes.length > MAX_NOTES) return null;
    for (const item of body.notes) {
      const note = readNote(item);
      if (note === null) return null;
      notes.push(note);
    }
  }
  if (body.studied_on === undefined) return { ranges, notes };
  if (typeof body.studied_on !== "string") return null;
  return { ranges, notes, studied_on: body.studied_on };
}
