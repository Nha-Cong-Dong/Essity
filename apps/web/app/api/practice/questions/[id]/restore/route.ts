import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// T8.7b (US-16 AC3): "Hoàn tác" of "Gỡ khỏi luyện tập"; the question is served again.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, question_id) => core.POST("/v1/practice/questions/{question_id}/restore", { params: { path: { question_id } } }),
    { route: "attempt", notFound: "question_not_found" },
  );
});
