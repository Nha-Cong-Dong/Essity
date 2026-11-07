import type { StackCard } from "@/components/subjects/review-stack";

// TODAY-REVIEW-ONLY: "Ôn tập hôm nay" lists review cards only. Practice questions are scheduled
// separately (their own block); a card with no question text still gets a name (its reason).
type Item = { question_id: string; subject_id: string; why: string; item_kind?: "card" | "practice"; front?: string | null; back?: string | null };

export function reviewCards(items: Item[], subjectId?: string): StackCard[] {
  return items
    .filter((i) => (i.item_kind ?? "card") === "card" && (subjectId === undefined || i.subject_id === subjectId))
    .map((i) => ({ id: i.question_id, why: i.why, kind: "card" as const, front: i.front?.trim() || i.why, back: i.back }));
}
