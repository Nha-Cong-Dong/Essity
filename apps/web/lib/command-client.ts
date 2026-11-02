// T9.3 (US-18): the browser's side of the command bar. `run` and `undo` are the two props of
// CommandBar, backed by web's routes (app/api/commands). Pure of server code: a client component
// uses it. The sentence is composed here from the structured diff; nothing the server says is shown
// as text.
import type { Diff } from "@/components/command/logic";
import type { Command, Outcome, UndoOutcome, UnclearReason } from "@/components/command/types";

export type DiffItem = { kind: string; id: string | null; verb: string; before: unknown; after: unknown };
type Applied = { status: "applied" | "undone"; diff: DiffItem[]; affected: number; op_kinds: string[] };
type Unclear = { status: "unclear"; reason: UnclearReason };

const WORDS: Record<string, Pick<Diff, "verb" | "noun" | "tail">> = {
  card_edit: { verb: "sửa", noun: "thẻ" },
  card_merge: { verb: "gộp", noun: "thẻ" },
  card_split: { verb: "tách", noun: "thẻ" },
  card_add: { verb: "thêm", noun: "thẻ" },
  card_discard_draft: { verb: "bỏ", noun: "thẻ nháp" },
  card_add_idea: { verb: "thêm ý vào", noun: "thẻ" },
  section_set_pages: { verb: "đổi", noun: "trang của mục" },
  section_exclude: { verb: "bỏ", noun: "mục", tail: "khỏi đề cương thi" },
  section_mark: { verb: "đánh dấu", noun: "mục" },
  suggest_only_subject: { verb: "chỉ gợi ý", noun: "môn này" },
  suggest_defer_subject: { verb: "hoãn gợi ý", noun: "môn này" },
  question_set_type: { verb: "đổi dạng", noun: "câu" },
  question_relink: { verb: "gắn lại", noun: "câu" },
  question_set_answer: { verb: "sửa đáp án", noun: "câu" },
  question_remove_from_practice: { verb: "bỏ", noun: "câu", tail: "khỏi luyện tập" },
};
const GENERIC = { verb: "đổi", noun: "mục" };

// The text of a card or an answer, the only fields shown as "từ … thành …" (one changed object).
const SHOWN = ["text", "answer_text"] as const;

function pair(item: DiffItem | undefined): Pick<Diff, "from" | "to"> {
  const before = item?.before as Record<string, unknown> | null | undefined;
  const after = item?.after as Record<string, unknown> | null | undefined;
  for (const key of SHOWN) {
    const from = before?.[key];
    const to = after?.[key];
    if (typeof from === "string" && typeof to === "string" && from !== to) return { from, to };
  }
  return {};
}

export function diffOf(out: Applied): Diff {
  const words = WORDS[out.op_kinds[0] ?? ""] ?? GENERIC;
  return {
    ...words,
    count: Math.max(1, out.affected),
    ...(out.diff.length === 1 ? pair(out.diff[0]) : {}),
  };
}

// An undo refused: a short, neutral reason that finishes "Không hoàn tác được: …".
const UNDO_REASON: Record<string, string> = {
  not_latest: "đã có lệnh mới hơn lệnh này",
  changed_after: "nội dung đã được sửa sau lệnh này",
  unitchangedelsewhere: "thẻ vừa được lưu ở màn khác",
  other_session: "lệnh này làm ở màn khác",
  conflict: "dữ liệu vừa đổi, thử lại sau",
  nothing_to_undo: "lệnh này đã được hoàn tác",
  not_owned: "không tìm thấy lệnh này",
};

async function post(path: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const json: unknown = await response.json().catch(() => null);
  return { status: response.status, json };
}

const codeOf = (json: unknown): string => (json as { error?: string } | null)?.error ?? "";

// A refusal that left nothing changed: the parser could not run, or core-api said no before writing.
const BEFORE_WRITE = new Set(["ai_disabled", "parse_unavailable", "parse_invalid", "email_not_verified"]);

export type LiveOptions = {
  subjectId: string;
  screenSessionId: string;
  /** After a command applied or was undone: the screen reads its data again. */
  changed: () => void;
  signedOut: () => void;
};

export function liveCommands({ subjectId, screenSessionId, changed, signedOut }: LiveOptions) {
  // The ids of the applied, not-undone commands, newest last: the bar's own stack, by id.
  const ids: string[] = [];

  async function run(command: Command, signal: AbortSignal): Promise<Outcome> {
    let reply;
    try {
      reply = await post(
        "/api/commands",
        { command_id: command.id, screen_session_id: screenSessionId, subject_id: subjectId, text: command.text },
        signal,
      );
    } catch {
      return { kind: "error", certain: false };
    }
    const { status, json } = reply;
    if (status === 401) {
      signedOut();
      return { kind: "error", certain: true };
    }
    if (status === 429 && codeOf(json) === "quota_hard_cap") return { kind: "pending-ai" };
    if (status === 200) {
      const out = json as Applied | Unclear | null;
      if (out?.status === "unclear") return { kind: "unclear", reason: out.reason };
      if (out?.status === "applied") {
        ids.push(command.id);
        changed();
        return { kind: "done", diff: diffOf(out) };
      }
      return { kind: "error", certain: false };
    }
    const code = codeOf(json);
    if (code === "unsupported") return { kind: "not-allowed" };
    // A 4xx or a refusal before any write: nothing changed. Anything else (5xx, lost): unknown.
    return { kind: "error", certain: (status >= 400 && status < 500) || BEFORE_WRITE.has(code) };
  }

  async function undo(signal: AbortSignal): Promise<UndoOutcome> {
    const id = ids.at(-1);
    if (id === undefined) return { kind: "undo-failed", reason: UNDO_REASON.nothing_to_undo! };
    const { status, json } = await post(`/api/commands/${id}/undo`, undefined, signal);
    if (status === 200 && (json as { status?: string } | null)?.status === "undone") {
      ids.pop();
      changed();
      return { kind: "undone" };
    }
    if (status === 401) {
      signedOut();
      throw new Error("signed_out");
    }
    const reason = UNDO_REASON[codeOf(json)];
    // Not a known refusal: the bar shows its "not sure" sentence (a throw is a timeout there).
    if (reason === undefined) throw new Error("undo_unknown");
    return { kind: "undo-failed", reason };
  }

  return { run, undo };
}
