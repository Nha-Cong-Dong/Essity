import type { components } from "@/lib/core-client"; // types only: erased from the browser bundle

// T4.18 (US-02 AC11): the browser's side of "đang soạn câu hỏi". The state lives in core-api; this
// reads it (GET /api/sessions/{id}/progress), polls with a growing wait and stops at an end state.

export type Progress = components["schemas"]["ProgressOut"];

export const FIRST_DELAY_MS = 2000;
export const MAX_DELAY_MS = 15000;
/** Reads that failed in a row before the screen says it cannot see the state. */
export const MAX_FAILURES = 5;

/** The wait before read number `attempt` (0-based): 2, 3, 4.5, 6.75 ... seconds, at most 15. */
export function nextDelay(attempt: number): number {
  return Math.min(Math.round(FIRST_DELAY_MS * 1.5 ** attempt), MAX_DELAY_MS);
}

export const isEnd = (progress: Progress): boolean => progress.state === "done" || progress.state === "failed";

export type ProgressResult = { ok: true; data: Progress } | { ok: false; code: string };

export async function fetchProgress(sessionId: string, signal?: AbortSignal): Promise<ProgressResult> {
  let response: Response;
  try {
    response = await fetch(`/api/sessions/${sessionId}/progress`, { cache: "no-store", signal });
  } catch {
    return { ok: false, code: "unavailable" };
  }
  const body: unknown = await response.json().catch(() => undefined);
  if (response.ok && typeof body === "object" && body !== null && "state" in body) {
    return { ok: true, data: body as Progress };
  }
  if (response.status === 401) return { ok: false, code: "signed_out" };
  if (response.status === 404) return { ok: false, code: "session_not_found" };
  return { ok: false, code: "unavailable" };
}

const STEPS: Record<NonNullable<Progress["step"]>, string> = {
  reading_notes: "Đang đọc ghi chú của bạn",
  splitting_units: "Đang chia thành các mảnh kiến thức",
  anchoring: "Đang đối chiếu với trang tài liệu",
  writing_questions: "Đang soạn câu hỏi",
};

// Placeholder sentences (data-copy="tam", R09) until the user approves them.
const FAILURES: Record<NonNullable<Progress["reason"]>, string> = {
  unreadable: "Chưa đọc được ghi chú này. Bạn thử lại với ảnh rõ hơn nhé.",
  llm_unavailable: "Chưa soạn được câu hỏi lúc này. Buổi học vẫn được lưu.",
  internal_error: "Chưa soạn được câu hỏi. Buổi học vẫn được lưu.",
};

/** The one sentence for a state. */
export function progressLine(progress: Progress): string {
  if (progress.state === "done") return "Đã soạn xong câu hỏi từ buổi học này.";
  if (progress.state === "failed") return FAILURES[progress.reason ?? "internal_error"];
  if (progress.state === "waiting" || !progress.step) return "Đang chờ đến lượt soạn câu hỏi";
  return STEPS[progress.step];
}
