"use client";

import { Button } from "@/components/ui/button";
import type { Submission } from "@/lib/session-study/round";

import { Notice } from "./session-parts";

// T7.12a (US-02 AC9-AC11; DESIGN.md §6.7 vùng 3, PRD §8.1 D8; design decisions C5, C9): what the
// user sees while the submission is read. One polite live region, updated only when the state
// changes. No clock and no "còn ~x phút". A whole failure and the AI limit stay here; a partly
// read submission goes on to the cards (see ReviewArea).

export function ProcessingArea({
  submission,
  onRetry,
  onManual,
}: {
  submission: Submission;
  onRetry: () => void;
  onManual: () => void;
}) {
  if (submission === "failed") {
    return (
      <div role="status" aria-live="polite">
        <Notice>
          <p className="m-0">Chưa đọc được bài nộp. Bài của bạn vẫn được giữ.</p>
          <div className="flex flex-wrap gap-3">
            <Button type="button" variant="secondary" onClick={onRetry}>
              Thử lại
            </Button>
            <Button type="button" variant="secondary" onClick={onManual}>
              Thêm thẻ
            </Button>
          </div>
        </Notice>
      </div>
    );
  }
  if (submission === "pending_ai") {
    return (
      <div role="status" aria-live="polite">
        <Notice>
          <p className="m-0">
            Hôm nay hệ thống đã hết lượt AI. Bài nộp của bạn được giữ và sẽ được đọc khi có lượt. Bạn vẫn thêm và sửa thẻ
            bằng tay được.
          </p>
          <Button type="button" variant="secondary" onClick={onManual}>
            Thêm thẻ
          </Button>
        </Notice>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p role="status" aria-live="polite" className="m-0 text-body">
        {submission === "queued" ? "Đang chờ đọc bài nộp…" : "Đang đọc bài nộp…"}
      </p>
      <div aria-hidden="true" className="flex flex-col gap-3">
        {[0, 1, 2].map((n) => (
          <div key={n} className="h-20 rounded-sheet bg-sunken motion-safe:animate-pulse" />
        ))}
      </div>
      <p className="m-0 text-meta text-ink-soft">Bạn rời màn này được, bài nộp vẫn được xử lý.</p>
    </div>
  );
}
