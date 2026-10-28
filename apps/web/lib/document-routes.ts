import "server-only";

import type { NextRequest } from "next/server";

import { type CoreClient, coreClientFor } from "@/lib/core-client";
import { errorResponse, rateLimited, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// T4.6: web's routes for a PDF upload. Each passes one call on to core-api (T4.5) and answers its
// JSON, or the code of its refusal. The file itself never comes here: the browser sends it straight
// to storage. The signed URL is in the answer to the browser and in no log (ADR-0013).

// core-api's refusals the screen tells apart; anything else is "unavailable".
const CODES = new Set([
  "content_mismatch",
  "document_not_found",
  "file_too_large",
  "invalid_filename",
  "not_indexed",
  "size_mismatch",
  "storage_full",
  "storage_quota_exceeded",
  "storage_unavailable",
  "toc_invalid",
  "subject_not_found",
  "unsupported_file_type",
  "upload_incomplete",
]);

type CoreResult = { data?: unknown; error?: unknown; response: Response };

/** Calls core-api for the signed-in user on `id` (a UUID, or 404 without a call). */
export async function forwardDocument(
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
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string" && CODES.has(detail)) return errorResponse(detail, response.status);
  if (response.status === 422) return errorResponse("invalid_request", 422);
  return unavailable("documents");
}
