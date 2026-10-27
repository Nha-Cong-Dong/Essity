import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// T2.19 (US-09 AC4): "Bỏ câu này", one tap; the question never comes back.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, question_id) => core.POST("/v1/questions/{question_id}/drop", { params: { path: { question_id } } }),
    { route: "attempt", notFound: "question_not_found" },
  );
});
