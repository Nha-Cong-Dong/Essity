// T7.12 (US-02 AC2-AC4, AC11, AC13; US-02b AC6-AC9): the browser's side of the study session. Each
// action is one call to web's own routes (app/api), which pass it on to core-api. An
// answer is `{ok}` or the code of the refusal, never a throw
// (a dropped network is `status: 0`, `error: "network"`). The learner's words are not logged.
import { type FileRef, type FileState, uploadSubmissionFile } from "./files";
import type { DocRef, Mention } from "./mention";

/** Where the submission stands: `none` = nothing was handed in yet. */
export type Phase = "none" | "queued" | "processing" | "pending_ai" | "failed" | "done";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; docId?: string };

export function readStatus(status: string | null): Phase {
  switch (status) {
    case null:
      return "none";
    case "queued":
    case "processing":
    case "pending_ai":
    case "failed":
    case "done":
      return status;
    default:
      return "processing";
  }
}

/** F2: one piece the learner wrote down ("Ghi lại"), kept at once. */
export type Piece = { id: string; position: number; text: string; fileCount: number };

export type SessionApi = {
  sessionId: string;
  /** F2: the pieces kept so far. */
  pieces(): Promise<ApiResult<{ pieces: Piece[]; submitted: boolean }>>;
  /** F2: "Ghi lại": keep one piece now. */
  /** Drop a piece kept by mistake, before the session is handed in. */
  removePiece(pieceId: string): Promise<ApiResult<null>>;
  addPiece(text: string, mentions: readonly Mention[], files?: readonly FileRef[]): Promise<ApiResult<Piece>>;
  /** F3: "Hoàn thành": every piece goes in as one submission, the worker makes the cards. */
  complete(): Promise<ApiResult<{ status: Phase }>>;
  submit(text: string, mentions: readonly Mention[], files?: readonly FileRef[]): Promise<ApiResult<{ status: Phase }>>;
  /** T7.12c: one file to storage; the last state is "ready" (what the submission names) or "failed". */
  upload(file: File, onState: (state: FileState) => void): Promise<void>;
  /** CARDS-V3: where the handed-in session stands; the cards are already in the Kho when it is done. */
  result(): Promise<ApiResult<{ phase: Phase; title: string | null; cards: number; notice: string | null }>>;
};

export function createSessionApi(sessionId: string, _docs: readonly DocRef[], fetchFn: typeof fetch = fetch, sectionId?: string): SessionApi {
  async function call(path: string, method: string, body?: unknown): Promise<{ status: number; json: Record<string, unknown> }> {
    try {
      const response = await fetchFn(path, {
        method,
        credentials: "same-origin",
        headers: body === undefined ? undefined : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const json = (await response.json().catch(() => ({}))) as Record<string, unknown>;
      return { status: response.status, json };
    } catch {
      return { status: 0, json: { error: "network" } };
    }
  }

  async function run<T>(path: string, method: string, body: unknown, read: (json: Record<string, unknown>) => T): Promise<ApiResult<T>> {
    const { status, json } = await call(path, method, body);
    if (status >= 200 && status < 300) return { ok: true, data: read(json) };
    return { ok: false, status, error: typeof json.error === "string" ? json.error : "unavailable" };
  }

  type CorePiece = { id: string; position: number; text: string; file_count: number };
  const piece = (p: CorePiece): Piece => ({ id: p.id, position: p.position, text: p.text, fileCount: p.file_count });

  return {
    sessionId,
    pieces: () =>
      run(`/api/sessions/${sessionId}/pieces`, "GET", undefined, (json) => ({
        pieces: (json.pieces as CorePiece[]).map(piece),
        submitted: json.submitted === true,
      })),
    addPiece: (text, mentions, files = []) =>
      run(
        `/api/sessions/${sessionId}/pieces`,
        "POST",
        { text, mentions: mentions.map((m) => ({ document_id: m.docId, start: m.start, end: m.end })), files },
        (json) => piece(json as unknown as CorePiece),
      ),
    removePiece: (pieceId) => run(`/api/sessions/${sessionId}/pieces/${pieceId}`, "DELETE", undefined, () => null),
    complete: () => run(`/api/sessions/${sessionId}/complete`, "POST", sectionId ? { section_id: sectionId } : undefined, (json) => ({ status: readStatus(String(json.status)) })),
    async submit(text, mentions, files = []) {
      const body = { session_id: sessionId, description: text, mentions: mentions.map((m) => ({ document_id: m.docId, start: m.start, end: m.end })), ...(files.length > 0 ? { files } : {}) };
      const { status, json } = await call("/api/submissions", "POST", body);
      if (status >= 200 && status < 300) return { ok: true, data: { status: readStatus(String(json.status)) } };
      const error = typeof json.error === "string" ? json.error : "unavailable";
      const at = typeof json.mention === "number" ? mentions[json.mention] : undefined;
      return at ? { ok: false, status, error, docId: at.docId } : { ok: false, status, error };
    },
    upload: (file, onState) => uploadSubmissionFile(sessionId, file, onState),
    result: () =>
      run(`/api/sessions/${sessionId}/result`, "GET", undefined, (json) => ({
        phase: readStatus((json.submission_status as string | null) ?? null),
        title: typeof json.title === "string" ? json.title : null,
        cards: typeof json.cards === "number" ? json.cards : 0,
        notice: typeof json.notice === "string" ? json.notice : null,
      })),
  };
}
