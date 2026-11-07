import { expect, it } from "vitest";

import { reviewCards } from "@/lib/review-cards";

const base = { subject_id: "s1", why: "Đến hạn ôn" };

// Red when: a practice question shows up in today's review list.
it("TODAY-REVIEW-ONLY drops practice items", () => {
  const out = reviewCards([
    { ...base, question_id: "a", item_kind: "card", front: "Q1" },
    { ...base, question_id: "b", item_kind: "practice", front: "P1" },
  ]);
  expect(out.map((c) => c.id)).toEqual(["a"]);
});

// Red when: a card without question text renders blank.
it("TODAY-REVIEW-ONLY gives every card a title", () => {
  const out = reviewCards([
    { ...base, question_id: "a", front: null },
    { ...base, question_id: "b", front: "  " },
  ]);
  expect(out.map((c) => c.front)).toEqual(["Đến hạn ôn", "Đến hạn ôn"]);
});

it("TODAY-REVIEW-ONLY filters by subject", () => {
  const out = reviewCards([{ ...base, question_id: "a" }, { ...base, subject_id: "s2", question_id: "b" }], "s1");
  expect(out.map((c) => c.id)).toEqual(["a"]);
});
