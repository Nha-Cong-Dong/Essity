import { withOrigin } from "@/lib/csrf";
import { forwardDocument } from "@/lib/document-routes";

type Params = { params: Promise<{ id: string }> };

// T4.6: the file is in storage; core-api checks it and announces it to ai-service.
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  return forwardDocument(
    request,
    id,
    (core, document_id) =>
      core.POST("/v1/documents/{document_id}/confirm", { params: { path: { document_id } } }),
    "document_not_found",
  );
});
