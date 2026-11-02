import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// T8.7 (US-16 AC3): "Gỡ khỏi luyện tập", one tap; the question's schedule stops.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, question_id) => core.POST("/v1/practice/questions/{question_id}/worthless", { params: { path: { question_id } } }),
    { route: "attempt", notFound: "question_not_found" },
  );
});
