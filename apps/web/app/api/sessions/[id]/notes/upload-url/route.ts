import { withOrigin } from "@/lib/csrf";
import { errorResponse } from "@/lib/http";
import { forwardSession, readNote } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T4.13b (US-02 AC13): a URL to upload one note file (photo, PDF, text) of the draft session. The
// body is exactly what core-api asks; the file itself goes from the browser straight to storage.
// The signed URL is in the answer to the browser and in no log (ADR-0013).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = readNote(await request.json().catch(() => null));
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      core.POST("/v1/sessions/{session_id}/notes/upload-url", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
