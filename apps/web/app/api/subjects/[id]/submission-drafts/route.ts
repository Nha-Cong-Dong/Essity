import { withOrigin } from "@/lib/csrf";
import { forwardSession } from "@/lib/session-routes";

type Params = { params: Promise<{ id: string }> };

// T7.12 (US-02 AC13): an empty draft session of the subject, the place a submission is made.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardSession(
    request,
    id,
    (core, subject_id) =>
      core.POST("/v1/subjects/{subject_id}/submission-drafts", { params: { path: { subject_id } } }),
    { notFound: "subject_not_found" },
  );
});
