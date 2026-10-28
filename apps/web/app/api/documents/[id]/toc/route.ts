import type { NextRequest } from "next/server";

import { forwardDocument } from "@/lib/document-routes";

type Params = { params: Promise<{ id: string }> };

// T4.9: the table of contents of one document, as core-api relays it (a GET: no origin check, like
// the other reads). The page validates the JSON against toc.v1; this route only passes it on.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forwardDocument(
    request,
    id,
    (core, document_id) => core.GET("/v1/documents/{document_id}/toc", { params: { path: { document_id } } }),
    "document_not_found",
  );
}
