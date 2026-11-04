import { withOrigin } from "@/lib/csrf";
import { forwardDocument } from "@/lib/document-routes";

type UntypedPost = {
  POST: (path: string, init: object) => Promise<{ data?: unknown; error?: unknown; response: Response }>;
};
type Params = { params: Promise<{ id: string }> };

// OUTLINE-FIX3: read the document's outline again; core-api lays the new reading over the learner's
// progress and answers 202 while ai-service reads. Once per document per five minutes (429).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardDocument(
    request,
    id,
    // The path is not in the generated client yet (it is regenerated once, at the merge wave):
    // call it through the same client untyped, then drop the cast.
    (core, document_id) =>
      (core as unknown as UntypedPost).POST("/v1/documents/{document_id}/reextract-outline", {
        params: { path: { document_id } },
      }),
    "document_not_found",
  );
});
