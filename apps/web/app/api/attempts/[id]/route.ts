import type { NextRequest } from "next/server";

import { forward } from "@/lib/review-routes";

type Params = { params: Promise<{ id: string }> };

// T2.13: the attempt as the answer and result screens show it, after a reload too. Never grades.
export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, attempt_id) => core.GET("/v1/attempts/{attempt_id}", { params: { path: { attempt_id } } }),
    { route: "attempt", notFound: "attempt_not_found" },
  );
}
