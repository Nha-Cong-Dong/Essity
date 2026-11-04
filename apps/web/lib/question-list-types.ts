import type { components } from "@/lib/core-client";

// V19/V20 fields (unlock date, due today) are optional until packages/api-client is regenerated.
export type QuestionRow = components["schemas"]["BankQuestionOut"] & {
  unlocked_at?: string | null;
  due?: boolean;
};
export type QuestionListOut = Omit<components["schemas"]["QuestionListOut"], "questions"> & {
  questions: QuestionRow[];
  due_today?: number;
};
