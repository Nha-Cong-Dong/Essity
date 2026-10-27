import { Button } from "@/components/ui/button";
import { dayLabel } from "@/lib/today-copy";

// T2.17 (US-08 AC1, AC4; DESIGN.md §6.7, screens-html/screens/session-done.html): what the session
// came to, in numbers and a date. Stopping early is saved, not punished: no streak, no count of
// missed days, nothing red. "Ôn thêm" is the secondary button.

export function Summary({
  answered,
  total,
  correct,
  nextDay,
  busy,
  onLeave,
  onMore,
}: {
  answered: number;
  total: number;
  correct: number;
  nextDay: string | null;
  busy: boolean;
  onLeave: () => void;
  onMore: () => void;
}) {
  const stoppedEarly = answered < total;
  return (
    <div className="flex flex-col items-start gap-7">
      <h1 data-copy="tam" className="m-0 font-display text-title">
        {stoppedEarly ? "Đã lưu phần bạn làm" : "Xong phiên hôm nay"}
      </h1>
      {stoppedEarly && (
        <p data-copy="tam" className="m-0 text-read">
          {total - answered} câu còn lại sẽ quay về lần ôn sau.
        </p>
      )}
      <div className="grid w-full grid-cols-2 gap-4">
        <div className="rounded-tile bg-hong p-8">
          <p className="m-0 font-display text-mega" data-testid="answered">
            {answered}
          </p>
          <p data-copy="tam" className="m-0 mt-2 text-lead">
            câu đã làm
          </p>
        </div>
        <div className="rounded-tile border border-line p-8">
          <p className="m-0 font-display text-mega" data-testid="correct">
            {correct}
          </p>
          <p data-copy="tam" className="m-0 mt-2 text-lead text-ink-soft">
            câu đúng
          </p>
        </div>
      </div>
      {nextDay && (
        <p data-copy="tam" className="m-0 text-read">
          Phiên tiếp theo: <b>{dayLabel(nextDay)}</b>
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="button" pending={busy} onClick={onLeave} data-copy="tam">
          Về trang chính
        </Button>
        <Button type="button" variant="secondary" disabled={busy} onClick={onMore} data-copy="tam">
          Ôn thêm
        </Button>
      </div>
    </div>
  );
}
