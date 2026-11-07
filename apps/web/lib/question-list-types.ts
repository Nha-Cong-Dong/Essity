import type { components } from "@/lib/core-client";

/** A card that unlocked a question (PRACTICE-PREREQ). Until the generated client carries the
 *  field, it is declared here; `QuestionRow` accepts it as optional either way. */
export type PrereqCard = { id: string; title: string; summary: string };
export type QuestionRow = components["schemas"]["BankQuestionOut"] & { prerequisite_cards?: PrereqCard[] };

export type QuestionListOut = Omit<components["schemas"]["QuestionListOut"], "questions"> & { questions: QuestionRow[] };
