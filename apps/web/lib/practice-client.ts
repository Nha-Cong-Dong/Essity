import { call } from "@/lib/review-client";
import type { components } from "@/lib/core-client"; // types only: erased from the browser bundle

// T8.7 (US-16 AC2, AC3, AC5): the practice answer screen's calls to web's routes
// (app/api/practice/*). Same reply shape as review-client: a code on failure, never thrown.

export type PracticeView = components["schemas"]["PracticeView"];
export type PracticeType = components["schemas"]["PracticeTypeOut"];
export type PracticeAnswer = { answer_text: string; dont_remember: boolean; hidden_ms: number };

export type PracticeApi = typeof practiceApi;

export const practiceApi = {
  open: (questionId: string) => call<PracticeView>(`/api/practice/questions/${questionId}/open`, "POST"),
  saveDraft: (attemptId: string, answer: Omit<PracticeAnswer, "hidden_ms">) =>
    call<null>(`/api/practice/attempts/${attemptId}/draft`, "PUT", answer),
  submit: (attemptId: string, answer: PracticeAnswer) =>
    call<PracticeView>(`/api/practice/attempts/${attemptId}/submit`, "POST", answer),
  regrade: (attemptId: string) => call<PracticeView>(`/api/practice/attempts/${attemptId}/regrade`, "POST"),
  /** "Chấm sai": the learner's own verdict, a new grade of the attempt (US-09, US-16 AC10). */
  override: (gradeId: string, verdict: "correct" | "incorrect") =>
    call<PracticeView>(`/api/practice/grades/${gradeId}/override`, "POST", { verdict }),
  read: (attemptId: string) => call<PracticeView>(`/api/practice/attempts/${attemptId}`, "GET"),
  /** "Gỡ khỏi luyện tập": the question is never asked again and its schedule stops. */
  remove: (questionId: string) => call<null>(`/api/practice/questions/${questionId}/worthless`, "POST"),
  /** "Hoàn tác" of `remove`: the question is asked again and its schedule resumes. */
  restore: (questionId: string) => call<null>(`/api/practice/questions/${questionId}/restore`, "POST"),
};
