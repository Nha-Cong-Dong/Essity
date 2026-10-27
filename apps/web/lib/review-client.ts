import type { components } from "@/lib/core-client"; // types only: erased from the browser bundle

import { go } from "@/lib/navigate";

// T2.15, T2.13: the answer screen's calls to web's routes (app/api/attempts, app/api/review-sessions).
// Signed out sends the user to /login; any other failure comes back as its code, never thrown.

export type Current = components["schemas"]["CurrentOut"];
export type Done = components["schemas"]["DoneOut"];
export type AttemptView = components["schemas"]["AttemptView"];
export type Result = components["schemas"]["ResultOut"];
export type Draft = components["schemas"]["AttemptOut"];
export type Answer = { answer_text: string; dont_remember: boolean };

/** What ai-service grades at most (core-api's ANSWER_MAX, plan D-4): the box stops there. */
export const ANSWER_MAX = 4000;

export type Reply<T> = { ok: true; data: T } | { ok: false; error: string };

async function call<T>(path: string, method: string, body?: object): Promise<Reply<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    return { ok: false, error: "offline" };
  }
  if (response.status === 401) {
    go("/login");
    return { ok: false, error: "signed_out" };
  }
  if (response.status === 204) return { ok: true, data: null as T }; // a draft saved
  const json: unknown = await response.json().catch(() => null);
  if (response.ok && json !== null) return { ok: true, data: json as T };
  const error = (json as { error?: unknown } | null)?.error;
  return { ok: false, error: typeof error === "string" ? error : "unavailable" };
}

export type ReviewApi = typeof reviewApi;

export const reviewApi = {
  current: (sessionId: string) => call<Current | Done>(`/api/review-sessions/${sessionId}/current`, "GET"),
  open: (sessionId: string) => call<Draft>(`/api/review-sessions/${sessionId}/attempts`, "POST"),
  stop: (sessionId: string) => call<{ answered: number; total: number }>(`/api/review-sessions/${sessionId}/stop`, "POST"),
  saveDraft: (attemptId: string, answer: Answer) => call<null>(`/api/attempts/${attemptId}/draft`, "PUT", answer),
  submit: (attemptId: string, answer: Answer) => call<AttemptView>(`/api/attempts/${attemptId}/submit`, "POST", answer),
  regrade: (attemptId: string) => call<AttemptView>(`/api/attempts/${attemptId}/regrade`, "POST"),
  override: (gradeId: string, verdict: "correct" | "incorrect") =>
    call<AttemptView>(`/api/grades/${gradeId}/override`, "POST", { verdict }),
  drop: (questionId: string) => call<null>(`/api/questions/${questionId}/drop`, "POST"),
  read: (attemptId: string) => call<AttemptView>(`/api/attempts/${attemptId}`, "GET"),
};
