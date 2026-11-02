import type { NextRequest } from "next/server";

import { forward } from "@/lib/review-routes";

// T8.7: a practice attempt as the screen shows it (after a reload too). Never grades.
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, attempt_id) => core.GET("/v1/practice/attempts/{attempt_id}", { params: { path: { attempt_id } } }),
    { route: "attempt", notFound: "attempt_not_found" },
  );
}
