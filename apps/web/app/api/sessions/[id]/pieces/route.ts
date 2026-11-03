import type { NextRequest } from "next/server";

import type { CoreClient } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { readPiece } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// F2: the pieces of a study session. Typed loosely until the api-client is regenerated.
type Loose = {
  GET(path: string, init: unknown): Promise<{ data?: unknown; error?: unknown; response: Response }>;
  POST(path: string, init: unknown): Promise<{ data?: unknown; error?: unknown; response: Response }>;
};
const loose = (core: CoreClient) => core as unknown as Loose;

export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, session_id) => loose(core).GET("/v1/study-sessions/{session_id}/pieces", { params: { path: { session_id } } }),
    { notFound: "session_not_found" },
  );
}

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = readPiece(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) => loose(core).POST("/v1/study-sessions/{session_id}/pieces", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
