import type { Diff } from "@/components/command/logic";
import type { Outcome, Tray, UndoOutcome } from "@/components/command/types";

// T9.3a: fixed data for /design-preview/command-bar. T9.3 replaces it with the T9.2 API. The
// busiest state has one unbroken long name and a long old and new value.

export const SUBJECT = { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" };
export const EXAMPLE = "mục 3.4 kết thúc ở trang 80";
export const PRACTICE_EXAMPLE = "đổi câu 4 thành tự luận";
export const PRACTICE_EXHAUSTED =
  "Thanh lệnh tạm tắt vì hết lượt AI. Bạn vẫn sửa trực tiếp được, trừ đổi dạng câu và gắn lại câu.";

export const LONG_NAME = "Sosánhhaigiaothứcvậnchuyểnnângcao_tínhtoánđộtrễtruyềnvàthônglượng_kỳthi_chương_bảy_phầnhai";

export const PAGES: Diff = { verb: "đổi", noun: "trang kết thúc của mục", target: "3.4", count: 1, from: "78", to: "80" };
export const EXCLUDE: Diff = { verb: "bỏ", noun: "mục", tail: "khỏi đề cương thi", scope: "chương 7", count: 9 };
export const MANY: Diff = { verb: "đánh dấu đã học", noun: "mục", scope: "chương 3", count: 14 };
export const LONG: Diff = {
  verb: "sửa",
  noun: "thẻ",
  target: LONG_NAME + LONG_NAME,
  count: 1,
  from: "TCP là giao thức hướng kết nối, tin cậy, có kiểm soát luồng và tắc nghẽn " + LONG_NAME,
  to: "TCP bắt tay ba bước rồi truyền theo dòng byte có thứ tự " + LONG_NAME,
};

export type CommandState =
  | "idle"
  | "understanding"
  | "done"
  | "many"
  | "unclear"
  | "not-allowed"
  | "too-long"
  | "pending-ai"
  | "pending-ai-practice"
  | "error"
  | "error-unsure"
  | "undone"
  | "undone-previous"
  | "undo-failed"
  | "long";

export const COMMAND_STATE_IDS: CommandState[] = [
  "idle", "understanding", "done", "many", "unclear", "not-allowed", "too-long", "pending-ai",
  "pending-ai-practice", "error", "error-unsure", "undone", "undone-previous", "undo-failed", "long",
];

export type Initial = { tray: Tray; stack: Diff[]; text: string };

const TOO_LONG_TEXT = "đổi ".repeat(130);

export function initialFor(state: CommandState): Initial {
  const tray = (t: Tray, stack: Diff[] = [], text = ""): Initial => ({ tray: t, stack, text });
  switch (state) {
    case "idle":
      return tray({ kind: "idle" });
    case "understanding":
      return tray({ kind: "understanding" }, [], "bỏ chương 7 khỏi đề cương thi");
    case "done":
      return tray({ kind: "done", diff: EXCLUDE }, [EXCLUDE]);
    case "many":
      return tray({ kind: "done", diff: MANY }, [MANY]);
    case "unclear":
      return tray({ kind: "unclear", reason: "ambiguous" }, [PAGES], "sửa nó");
    case "not-allowed":
      return tray({ kind: "not-allowed" }, [], "xóa môn này");
    case "too-long":
      return tray({ kind: "too-long" }, [PAGES], TOO_LONG_TEXT);
    case "pending-ai":
    case "pending-ai-practice":
      return tray({ kind: "pending-ai" }, [PAGES], "mục 3.5 kết thúc ở trang 92");
    case "error":
      return tray({ kind: "error", certain: true }, [], "bỏ chương 7 khỏi đề cương thi");
    case "error-unsure":
      return tray({ kind: "error", certain: false }, [PAGES], "bỏ chương 7 khỏi đề cương thi");
    case "undone":
      return tray({ kind: "undone", diff: EXCLUDE });
    case "undone-previous":
      return tray({ kind: "undone", diff: EXCLUDE }, [PAGES]);
    case "undo-failed":
      return tray({
        kind: "undo-failed",
        reason: "thẻ này đã được sửa sau lệnh đó",
        ref: { kind: "card", id: "0b8f1d2e-0000-4000-8000-0000000000c1" },
      }, [LONG]);
    case "long":
      return tray({ kind: "done", diff: LONG }, [PAGES, LONG], LONG_NAME);
  }
}

// What the preview answers when a command is sent: "xóa…" is refused, "?" is unclear, the rest
// is applied. There is no wait on purpose that a test would have to sit through.
export function fakeRun(text: string): Outcome {
  if (/^xóa/iu.test(text)) return { kind: "not-allowed" };
  if (text.includes("?")) return { kind: "unclear", reason: "missing_info" };
  return { kind: "done", diff: PAGES };
}

export const fakeUndo = (): UndoOutcome => ({ kind: "undone" });
