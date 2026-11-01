// T7.12a (DESIGN.md §6.7 vùng 1-5; design decisions C2, C5, C9): where one study round is.
// `focus` is asked only after the user's own action (Gửi, Lưu, Học tiếp, Thử lại); a change that
// arrives in the background (the read finished) only sets `announce` for the live region, so it
// never takes the caret from a card being edited.

export type Phase = "compose" | "processing" | "review" | "saved";
export type Submission = "queued" | "processing" | "failed" | "pending_ai";

export type Round = {
  phase: Phase;
  round: number;
  /** Set while phase is "processing". */
  submission: Submission | null;
  /** The read missed some pages: review shows the note on top. */
  partialNote: boolean;
  /** The backend refused the part after this @ (document id), so the form shows it. */
  rejectedDoc: string | null;
  saveError: boolean;
  /** The region whose heading takes focus, or null. */
  focus: Phase | null;
  /** One sentence for the polite live region. */
  announce: string | null;
};

export const initialRound: Round = {
  phase: "compose",
  round: 1,
  submission: null,
  partialNote: false,
  rejectedDoc: null,
  saveError: false,
  focus: null,
  announce: null,
};

export type RoundEvent =
  | { type: "send" }
  | { type: "processing" }
  | { type: "scope-rejected"; docId: string }
  | { type: "drafts-ready"; count: number }
  | { type: "partial"; count: number }
  | { type: "failed" }
  | { type: "pending-ai" }
  | { type: "retry" }
  | { type: "manual" }
  | { type: "save-ok" }
  | { type: "save-error" }
  | { type: "continue" }
  /** T7.12: a send that could not be made, or a read to start over: the form again, text kept. */
  | { type: "back" };

export function roundReducer(state: Round, event: RoundEvent): Round {
  const quiet = { focus: null, announce: null } as const;
  switch (event.type) {
    case "send":
      return { ...state, ...quiet, phase: "processing", submission: "queued", rejectedDoc: null, focus: "processing" };
    case "processing":
      return { ...state, ...quiet, submission: "processing" };
    case "scope-rejected":
      return { ...state, ...quiet, phase: "compose", submission: null, rejectedDoc: event.docId, focus: "compose" };
    case "drafts-ready":
      return {
        ...state,
        ...quiet,
        phase: "review",
        submission: null,
        partialNote: false,
        announce: `Đã tách ${event.count} thẻ nháp.`,
      };
    case "partial":
      return {
        ...state,
        ...quiet,
        phase: "review",
        submission: null,
        partialNote: true,
        announce: `Đã tách ${event.count} thẻ nháp. Một vài trang chưa đọc được.`,
      };
    case "failed":
      return { ...state, ...quiet, phase: "processing", submission: "failed" };
    case "pending-ai":
      return { ...state, ...quiet, phase: "processing", submission: "pending_ai" };
    case "retry":
      return { ...state, ...quiet, phase: "processing", submission: "queued", partialNote: false, focus: "processing" };
    case "manual":
      return { ...state, ...quiet, phase: "review", submission: null, focus: "review" };
    case "save-ok":
      return { ...state, ...quiet, phase: "saved", saveError: false, focus: "saved" };
    case "save-error":
      return { ...state, ...quiet, saveError: true };
    case "back":
      return { ...state, ...quiet, phase: "compose", submission: null, focus: "compose" };
    case "continue":
      return { ...initialRound, round: state.round + 1, focus: "compose" };
  }
}
