"use client";

import { useState } from "react";

import { StartButton } from "@/components/today/start-button";

// D6, V18: this subject's cards due today, stacked. Each card shows the question and its answer.
// Click the top card: it moves to the bottom and the next shows. Viewing only: no remember/forgot
// grading here (that is the review session's job). "Ôn riêng môn này" starts that session.

export type StackCard = { id: string; why: string; kind: "card" | "practice"; front?: string | null; back?: string | null };

export function ReviewStack({ subjectId, cards }: { subjectId: string; cards: StackCard[] }) {
  const [order, setOrder] = useState(cards);
  if (order.length === 0) {
    return (
      <section className="flex min-w-0 flex-col items-start gap-3" aria-labelledby={`rv-${subjectId}`} data-review-empty>
        <h2 id={`rv-${subjectId}`} className="m-0 text-body font-semibold">
          Ôn tập hôm nay
        </h2>
        {/* mascot placeholder */}
        <div aria-hidden="true" data-mascot className="flex size-20 items-center justify-center rounded-full bg-sunken text-3xl">
          ☺
        </div>
        <p className="m-0 text-read">Tuyệt vời, không có kiến thức nào cần ôn hôm nay</p>
      </section>
    );
  }
  const shown = order.slice(0, 3);
  return (
    <section className="flex min-w-0 flex-col gap-3" aria-labelledby={`rv-${subjectId}`}>
      <h2 id={`rv-${subjectId}`} className="m-0 text-body font-semibold">
        Ôn tập hôm nay
        <span className="sr-only"> ({order.length} thẻ)</span>
      </h2>
      <div className="relative h-60 sm:h-56" data-review-stack>
        {shown
          .map((card, i) => ({ card, i }))
          .reverse()
          .map(({ card, i }) => (
            <button
              key={card.id}
              type="button"
              disabled={i !== 0}
              onClick={() => setOrder((o) => [...o.slice(1), o[0]!])}
              aria-label={i === 0 ? "Thẻ trên cùng: bấm để xem thẻ tiếp theo" : undefined}
              style={{ transform: `translate(${i * 10}px, ${i * 10}px)`, zIndex: 10 - i }}
              className="absolute inset-0 mr-3 mb-3 flex flex-col gap-3 overflow-hidden rounded-sheet border border-line bg-sheet p-4 text-left transition-transform duration-300 disabled:cursor-default"
            >
              <span className="inline-flex items-center gap-2 text-meta text-ink-soft">
                {card.kind === "practice" ? "Câu luyện tập" : "Thẻ ôn"}
              </span>
              <span className="line-clamp-3 font-display text-lead break-words">{card.front ?? card.why}</span>
              {card.back && (
                <span className="mt-auto flex flex-col gap-1 rounded-control bg-rose-50 p-3">
                  <span className="text-meta text-ink-soft">Đáp án</span>
                  <span className="line-clamp-4 text-body break-words">{card.back}</span>
                </span>
              )}
            </button>
          ))}
      </div>
      <div className="pt-2">
        <StartButton variant="secondary" subjectId={subjectId}>
          Ôn riêng môn này
        </StartButton>
      </div>
    </section>
  );
}
