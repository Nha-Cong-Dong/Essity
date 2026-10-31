import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { forwardOutline } from "@/lib/outline-routes";

type Params = { params: Promise<{ id: string }> };

// T7.5 (US-13 AC4): change one section's page range, `excluded` or `studied`; core-api checks the
// range rules and answers the whole outline.
const CHANGE = {
  first_page: { kind: "integer", optional: true },
  last_page: { kind: "integer", optional: true },
  excluded: { kind: "boolean", optional: true },
  studied: { kind: "boolean", optional: true },
} as const;

export const PATCH = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  const body = await readFields(request, CHANGE, { maxBytes: 512 });
  if (body === null || Object.keys(body).length === 0) return errorResponse("invalid_request", 400);
  return forwardOutline(
    request,
    id,
    (core, section_id) => core.PATCH("/v1/sections/{section_id}", { params: { path: { section_id } }, body }),
    "section_not_found",
  );
});
