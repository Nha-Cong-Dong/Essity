// T7.12a (DESIGN.md §6.7 vùng 1-5; design decisions C2, C5, C9): where one study round is.
// `focus` is asked only after the user's own action (Gửi, Lưu, Học tiếp, Thử lại); a change that
// arrives in the background (the read finished) only sets `announce` for the live region, so it
// never takes the caret from a card being edited.

export type Phase = "compose" | "processing" | "done";
export type Submission = "queued" | "processing" | "failed" | "pending_ai";

/** CARDS-V3: what a finished read made. The cards are already in the Kho; `notice` says why there are none. */
export type SessionResult = { cards: number; title: string | null; notice: string | null };

export type Round = {
  phase: Phase;
  round: number;
  /** Set while phase is "processing". */
  submission: Submission | null;
  /** Set when phase is "done". */
  result: SessionResult | null;
  /** The backend refused the part after this @ (document id), so the form shows it. */
  rejectedDoc: string | null;
  /** The region whose heading takes focus, or null. */
  focus: Phase | null;
  /** One sentence for the polite live region. */
  announce: string | null;
};

export const initialRound: Round = {
  phase: "compose",
  round: 1,
  submission: null,
  result: null,
  rejectedDoc: null,
  focus: null,
  announce: null,
};

export type RoundEvent =
  | { type: "send" }
  | { type: "processing" }
  | { type: "scope-rejected"; docId: string }
  | { type: "done"; result: SessionResult }
  | { type: "failed" }
  | { type: "pending-ai" }
  | { type: "retry" }
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
    case "done":
      return {
        ...state,
        ...quiet,
        phase: "done",
        submission: null,
        result: event.result,
        announce: event.result.cards > 0 ? `Đã thêm ${event.result.cards} thẻ vào Kho.` : "Chưa tìm thấy nội dung để làm thẻ.",
      };
    case "failed":
      return { ...state, ...quiet, phase: "processing", submission: "failed" };
    case "pending-ai":
      return { ...state, ...quiet, phase: "processing", submission: "pending_ai" };
    case "retry":
      return { ...state, ...quiet, phase: "processing", submission: "queued", focus: "processing" };
    case "back":
      return { ...state, ...quiet, phase: "compose", submission: null, focus: "compose" };
    case "continue":
      return { ...initialRound, round: state.round + 1, focus: "compose" };
  }
}

/** Where a session opened (or reopened) from the server stands: its status and, when done, its result. */
export function roundFromResult(status: "none" | "queued" | "processing" | "pending_ai" | "failed" | "done", result: SessionResult | null): Round {
  if (status === "done") return { ...initialRound, phase: "done", result: result ?? { cards: 0, title: null, notice: null } };
  if (status === "none") return initialRound;
  return { ...initialRound, phase: "processing", submission: status };
}
