import type { Diff, ObjectRef } from "@/components/command/logic";

// T9.3a (US-18; DESIGN §6.14): what the bar knows about a command's outcome. The shapes mirror
// ParseCommandResponse of ai-service (T9.1) and the structured diff T9.2 will return; there is
// no API yet, so fixtures and the preview supply them.

export type UnclearReason = "ambiguous" | "unknown_target" | "unsupported" | "missing_info";

export type Outcome =
  | { kind: "done"; diff: Diff; ref?: ObjectRef }
  | { kind: "unclear"; reason: UnclearReason }
  | { kind: "not-allowed" }
  | { kind: "pending-ai" }
  /** `certain`: core said nothing changed. Otherwise (timeout, 5xx, lost connection) it is unknown. */
  | { kind: "error"; certain: boolean };

export type UndoOutcome =
  | { kind: "undone" }
  | { kind: "undo-failed"; reason: string; ref?: ObjectRef };

export type Command = { id: string; text: string };

/** What the tray shows. The newest result only; the undo stack lives beside it. */
export type Tray =
  | { kind: "idle" }
  | { kind: "understanding" }
  | { kind: "done"; diff: Diff }
  | { kind: "unclear"; reason: UnclearReason }
  | { kind: "not-allowed" }
  | { kind: "too-long" }
  | { kind: "pending-ai" }
  | { kind: "error"; certain: boolean }
  | { kind: "undone"; diff: Diff }
  | { kind: "undo-failed"; reason: string; ref?: ObjectRef };
