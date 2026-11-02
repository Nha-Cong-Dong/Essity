import { forwardCommand } from "@/lib/command-routes";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, readFields } from "@/lib/http";
import { isSubjectId } from "@/lib/subject-id";

// T9.3 (US-18): one command as a line of text, applied once per `command_id`. The web sends text
// only (never ops): the parser and the validator live in core-api.
const COMMAND = {
  command_id: { kind: "string" },
  screen_session_id: { kind: "string" },
  subject_id: { kind: "string" },
  text: { kind: "string" },
} as const;

export const POST = withOrigin(async (request) => {
  const body = await readFields(request, COMMAND, { maxBytes: 8 * 1024 });
  if (
    body === null ||
    !isSubjectId(body.command_id) ||
    !isSubjectId(body.screen_session_id) ||
    !isSubjectId(body.subject_id)
  ) {
    return errorResponse("invalid_request", 400);
  }
  return forwardCommand(request, (core) => core.POST("/v1/commands", { body }));
});
