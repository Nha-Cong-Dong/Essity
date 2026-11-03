import { withOrigin } from "@/lib/csrf";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// F3: "Hoàn thành": all the pieces go in as one submission; the worker makes the cards.
type Loose = { POST(path: string, init: unknown): Promise<{ data?: unknown; error?: unknown; response: Response }> };

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      (core as unknown as Loose).POST("/v1/study-sessions/{session_id}/complete", { params: { path: { session_id } } }),
    { notFound: "session_not_found" },
  );
});
