import { withOrigin } from "@/lib/csrf";
import { forwardDocument } from "@/lib/document-routes";

type Params = { params: Promise<{ id: string }> };

// OUTLINE-FIX3: read the document's outline again; core-api lays the new reading over the learner's
// progress and answers 202 while ai-service reads. Once per document per five minutes (429).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardDocument(
    request,
    id,
    (core, document_id) =>
      core.POST("/v1/documents/{document_id}/reextract-outline", { params: { path: { document_id } } }),
    "document_not_found",
  );
});
