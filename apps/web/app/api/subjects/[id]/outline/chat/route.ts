import { forwardCommand } from "@/lib/command-routes";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { isSubjectId } from "@/lib/subject-id";

// E3: the outline chat. One sentence in plain Vietnamese; core-api reads it, applies it, and
// answers a short Vietnamese `reply`. The body is rebuilt field by field.
const CHAT = { text: { kind: "string" } } as const;

export const POST = withOrigin(async (request, { params }: { params: Promise<{ id: string }> }) => {
  const { id } = await params;
  const body = await readFields(request, CHAT, { maxBytes: 4 * 1024 });
  if (body === null || !isSubjectId(id) || body.text.trim() === "") return errorResponse("invalid_request", 400);
  // The path is typed once packages/api-client is regenerated with this endpoint (PR #194).
  const path = "/v1/subjects/{subject_id}/outline/chat" as never;
  return forwardCommand(request, (core) =>
    core.POST(path, { params: { path: { subject_id: id } }, body: { text: body.text } } as never),
  );
});
