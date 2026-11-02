import { forwardCommand } from "@/lib/command-routes";
import { withOrigin } from "@/lib/csrf";
import { errorResponse } from "@/lib/http";
import { isSubjectId } from "@/lib/subject-id";

type Params = { params: Promise<{ id: string }> };

// T9.3 (US-18 AC4): undo one command by its id (a UUID, or 400 without a call).
export const POST = withOrigin(async (request, { params }: Params) => {
  const { id } = await params;
  if (!isSubjectId(id)) return errorResponse("invalid_request", 400);
  return forwardCommand(request, (core) =>
    core.POST("/v1/commands/{command_id}/undo", { params: { path: { command_id: id } } }),
  );
});
