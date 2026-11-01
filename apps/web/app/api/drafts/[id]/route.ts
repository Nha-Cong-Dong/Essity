import type { NextRequest } from "next/server";

import { withOrigin } from "@/lib/csrf";
import { readEdit } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

const NOT_FOUND = { notFound: "unit_not_found" } as const;

// T7.12 (US-02b AC6, AC7): one card: read it (to reload after a 409), edit it in place with the
// version the browser saw as `If-Match`, discard it (undo is a separate route).
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, unit_id) => core.GET("/v1/drafts/{unit_id}", { params: { path: { unit_id } } }),
    NOT_FOUND,
  );
}

export const PATCH = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const edit = await readEdit(request);
  if (edit === null) return errorResponse("invalid_request", 400);
  const { version, ...body } = edit;
  return forwardSession(
    request,
    id,
    (core, unit_id) =>
      core.PATCH("/v1/drafts/{unit_id}", {
        params: { path: { unit_id }, header: { "if-match": String(version) } },
        body,
      }),
    NOT_FOUND,
  );
});

export const DELETE = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, unit_id) => core.DELETE("/v1/drafts/{unit_id}", { params: { path: { unit_id } } }),
    NOT_FOUND,
  );
});
