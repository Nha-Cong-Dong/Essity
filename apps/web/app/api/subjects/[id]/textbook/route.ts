import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forwardOutline } from "@/lib/outline-routes";
import { isSubjectId } from "@/lib/subject-id";

type Params = { params: Promise<{ id: string }> };

// T7.5 (US-01 AC5): make a document the subject's main textbook. `confirm` is true only after the
// learner agreed to the change (core-api answers 409 textbook_has_cards with the card count).
const SET = { document_id: { kind: "string" }, confirm: { kind: "boolean", optional: true } } as const;

export const PUT = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readFields(request, SET, { maxBytes: 512 });
  if (body === null || !isSubjectId(body.document_id)) return errorResponse("invalid_request", 400);
  const sent = { document_id: body.document_id, confirm: body.confirm === true };
  return forwardOutline(
    request,
    id,
    (core, subject_id) => core.PUT("/v1/subjects/{subject_id}/textbook", { params: { path: { subject_id } }, body: sent }),
    "subject_not_found",
  );
});
