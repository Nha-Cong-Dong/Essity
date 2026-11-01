import { withOrigin } from "@/lib/csrf";
import { readSave } from "@/lib/draft-routes";
import { errorResponse } from "@/lib/http";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02b AC9): "Lưu". The cards the screen shows, each with the version it saw; one
// transaction in core-api, 409 `unit_changed_elsewhere` when any card changed elsewhere.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = readSave(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/sessions/{session_id}/drafts/save", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
