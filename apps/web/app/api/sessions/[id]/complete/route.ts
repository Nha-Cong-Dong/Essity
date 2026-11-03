import { withOrigin } from "@/lib/csrf";
import { isSubjectId } from "@/lib/subject-id";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// F3: "Hoàn thành": all the pieces go in as one submission; the worker makes the cards.
type Loose = { POST(path: string, init: unknown): Promise<{ data?: unknown; error?: unknown; response: Response }> };

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const raw = (await request.json().catch(() => null)) as { section_id?: unknown } | null;
  const body = typeof raw?.section_id === "string" && isSubjectId(raw.section_id) ? { section_id: raw.section_id } : undefined;
  return forwardSession(
    request,
    id,
    (core, session_id) =>
      (core as unknown as Loose).POST("/v1/study-sessions/{session_id}/complete", { params: { path: { session_id } }, body }),
    { notFound: "session_not_found" },
  );
});
