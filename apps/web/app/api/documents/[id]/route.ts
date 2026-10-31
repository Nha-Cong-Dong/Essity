import type { NextRequest } from "next/server";

import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forwardOutline } from "@/lib/outline-routes";

type Params = { params: Promise<{ id: string }> };

// T7.5 (US-01 AC4, AC7): a document's role (textbook / question_bank / auxiliary) or short name.
// A role of "textbook" never overwrites an existing one here: core-api answers 409 textbook_exists
// and the screen goes through PUT /api/subjects/[id]/textbook after the learner confirmed.
const CHANGE = { role: { kind: "string", optional: true }, short_name: { kind: "string", optional: true } } as const;
const ROLES = new Set(["textbook", "question_bank", "auxiliary"]);

export const PATCH = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const fields = await readFields(request, CHANGE, { maxBytes: 1024 });
  if (fields === null || Object.keys(fields).length === 0) return errorResponse("invalid_request", 400);
  if (fields.role !== undefined && !ROLES.has(fields.role)) return errorResponse("invalid_request", 400);
  const body = {
    ...(fields.role !== undefined ? { role: fields.role as "textbook" | "question_bank" | "auxiliary" } : {}),
    ...(fields.short_name !== undefined ? { short_name: fields.short_name } : {}),
  };
  return forwardOutline(
    request,
    id,
    (core, document_id) => core.PATCH("/v1/documents/{document_id}", { params: { path: { document_id } }, body }),
    "document_not_found",
  );
});

// T7.5: one document with its status, polled by the upload form until a textbook is readable
// (a GET: no origin check).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardOutline(
    request,
    id,
    (core, document_id) => core.GET("/v1/documents/{document_id}", { params: { path: { document_id } } }),
    "document_not_found",
  );
}
