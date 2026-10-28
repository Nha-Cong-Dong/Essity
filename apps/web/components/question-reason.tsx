import type { Current } from "@/lib/review-client";

export type Reason = Extract<Current, { question: unknown }>["question"]["reason"];

/**
 * T5.4 (US-07): "Vì sao câu này?" under the question, closed until the learner opens it
 * (screens-html/screens/answer.html). The server sends data, never words: the sentence is written
 * here, neutral, no comparison and no pressure (DESIGN.md §4). Every question has a reason.
 */
export function QuestionReason({ reason }: { reason: Reason }) {
  const percent = Math.round((reason.retrievability ?? 0) * 100);
  const days = reason.days_since_last ?? 0;
  return (
    <details className="mt-2.5 min-w-0">
      <summary className="cursor-pointer text-meta text-ink-soft underline">Vì sao câu này?</summary>
      <div className="mt-2 rounded-lg bg-subtle p-3 text-meta wrap-anywhere">
        {reason.kind === "new" ? (
          <p data-copy="tam" className="m-0">
            Câu mới, bạn chưa ôn lần nào.
          </p>
        ) : days === 0 ? (
          <p data-copy="tam" className="m-0">
            Khả năng bạn còn nhớ khoảng {percent}%, lần ôn trước là hôm nay.
          </p>
        ) : (
          <p data-copy="tam" className="m-0">
            Khả năng bạn còn nhớ khoảng {percent}%, lần ôn trước cách đây {days} ngày.
          </p>
        )}
      </div>
    </details>
  );
}
