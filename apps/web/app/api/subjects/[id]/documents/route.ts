import { withOrigin } from "@/lib/csrf";
import { forwardDocument } from "@/lib/document-routes";
import { errorResponse, readFields } from "@/lib/http";

type Params = { params: Promise<{ id: string }> };

// T4.6 (US-01): a URL to upload one PDF to the subject. The body is exactly what core-api asks.
const ASK = { filename: { kind: "string" }, size_bytes: { kind: "integer" }, sha256: { kind: "string" } } as const;

export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readFields(request, ASK, { maxBytes: 2048 });
  if (body === null) return errorResponse("invalid_request", 400);
  return forwardDocument(
    request,
    id,
    (core, subject_id) =>
      core.POST("/v1/subjects/{subject_id}/documents", { params: { path: { subject_id } }, body }),
    "subject_not_found",
  );
});
