import { withOrigin } from "@/lib/csrf";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02b AC8): "Hoàn tác" a discarded card (core-api keeps it 7 days).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, unit_id) => core.POST("/v1/drafts/{unit_id}/undo", { params: { path: { unit_id } } }),
    { notFound: "unit_not_found" },
  );
});
