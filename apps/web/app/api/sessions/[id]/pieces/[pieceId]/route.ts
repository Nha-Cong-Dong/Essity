import type { CoreClient } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";
import { isSubjectId } from "@/lib/subject-id";

type Params = { params: Promise<{ id: string; pieceId: string }> };

// Typed loosely until the api-client is regenerated for the new route.
type Loose = {
  DELETE(path: string, init: unknown): Promise<{ data?: unknown; error?: unknown; response: Response }>;
};
const loose = (core: CoreClient) => core as unknown as Loose;

/** Drop a piece kept by mistake, before the session is handed in (a piece `complete` refuses). */
export const DELETE = withOrigin(async (request, { params }: Params) => {
  const { id, pieceId } = await params;
  if (!isSubjectId(pieceId)) return errorResponse("piece_not_found", 404);
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      loose(core).DELETE("/v1/study-sessions/{session_id}/pieces/{piece_id}", {
        params: { path: { session_id, piece_id: pieceId } },
      }),
    { notFound: "session_not_found" },
  );
});
