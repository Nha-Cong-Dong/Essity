import { withOrigin } from "@/lib/csrf";
import { forward } from "@/lib/review-routes";

// T8.7 (US-16 AC2): serve a practice question: its open draft, made if there is none.
export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  return forward(
    request,
    id,
    (core, question_id) => core.POST("/v1/practice/questions/{question_id}/open", { params: { path: { question_id } } }),
    { route: "attempt", notFound: "question_not_found", timeoutMs: 25_000 }, // may draft the answer with the AI once
  );
});
