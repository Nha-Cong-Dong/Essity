"use client";

import { useState } from "react";

import { StartButton } from "@/components/today/start-button";
import { Sheet } from "@/components/ui/sheet";

// Hackathon D6: this subject's cards due today, stacked. Click the top card: it slides to the
// bottom and the next one shows. "Ôn riêng môn này" starts a review session for this subject only.

export type StackCard = { id: string; why: string; kind: "card" | "practice" };

export function ReviewStack({ subjectId, cards }: { subjectId: string; cards: StackCard[] }) {
  const [order, setOrder] = useState(cards);
  if (order.length === 0) {
    return (
      <Sheet variant="tile" className="flex min-w-0 flex-col items-start gap-3" aria-labelledby={`rv-${subjectId}`} data-review-empty>
        <h2 id={`rv-${subjectId}`} className="m-0 font-display text-lead">
          Ôn tập hôm nay
        </h2>
        {/* mascot placeholder */}
        <div aria-hidden="true" data-mascot className="flex size-20 items-center justify-center rounded-full bg-sunken text-3xl">
          ☺
        </div>
        <p className="m-0 text-read">Tuyệt vời, không có kiến thức nào cần ôn hôm nay</p>
      </Sheet>
    );
  }
  const shown = order.slice(0, 3);
  return (
    <Sheet variant="tile" className="flex min-w-0 flex-col gap-3" aria-labelledby={`rv-${subjectId}`}>
      <h2 id={`rv-${subjectId}`} className="m-0 font-display text-lead">
        Ôn tập hôm nay
        <span className="ml-2 text-meta font-normal text-ink-soft">{order.length} thẻ</span>
      </h2>
      <div className="relative h-40" data-review-stack>
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
              style={{ transform: `translate(${i * 8}px, ${i * 8}px)`, zIndex: 10 - i }}
              className="absolute inset-0 flex flex-col items-start justify-between rounded-tile bg-paper p-4 text-left shadow-sheet inset-ring-1 inset-ring-line transition-transform duration-300 disabled:cursor-default"
            >
              <span className="text-meta text-ink-soft">{card.kind === "practice" ? "Câu luyện tập" : "Thẻ ôn"}</span>
              <span className="text-read wrap-anywhere">{card.why}</span>
            </button>
          ))}
      </div>
      <div className="pt-2">
        <StartButton variant="secondary" subjectId={subjectId}>
          Ôn riêng môn này
        </StartButton>
      </div>
    </Sheet>
  );
}
