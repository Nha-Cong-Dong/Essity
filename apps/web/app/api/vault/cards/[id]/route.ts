import type { NextRequest } from "next/server";

import { withOrigin } from "@/lib/csrf";
import { errorResponse } from "@/lib/http";
import { forwardCard, readCardEdit } from "@/lib/vault-routes";

type Params = { params: Promise<{ id: string }> };

// G3: "Sửa thẻ" -> Lưu (PATCH) and delete on a vault card.
export const PATCH = withOrigin(async (request: NextRequest, { params }: Params) => {
  const { id } = await params;
  const edit = readCardEdit(await request.json().catch(() => null));
  if (edit === null) return errorResponse("invalid_request", 400);
  return forwardCard(request, id, "PATCH", "", edit);
});

export const DELETE = withOrigin(async (request: NextRequest, { params }: Params) => {
  const { id } = await params;
  return forwardCard(request, id, "DELETE");
});
