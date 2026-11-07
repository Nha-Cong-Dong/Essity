import { Mascot } from "@/components/mascot";
import { Block } from "@/components/screen-kit";
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
      {stoppedEarly ? (
        <h1 data-copy="tam" className="m-0 font-display text-title">
          Đã lưu phần bạn làm
        </h1>
      ) : (
        <h1 data-copy="tam" className="m-0 font-display text-title">
          Xong phiên hôm nay
        </h1>
      )}
      {stoppedEarly && (
        <p data-copy="tam" className="m-0 text-read">
          {total - answered} câu còn lại sẽ quay về lần ôn sau.
        </p>
      )}
      <div className="grid w-full gap-4 min-[641px]:grid-cols-2">
        <Block tier="field" className="relative flex flex-col justify-between gap-2 overflow-hidden p-6 min-[641px]:p-8">
          <div>
            <p className="m-0 font-display text-mega" data-testid="answered">
              {answered}
            </p>
            <p data-copy="tam" className="m-0 mt-2 text-lead text-on-plum-soft">
              câu đã làm
            </p>
          </div>
          <Mascot kind="sun" pose="khen" size="sm" tone="solid" className="absolute right-3 bottom-0" />
        </Block>
        <Block tier="sheet" className="p-6 min-[641px]:p-8">
          <p className="m-0 font-display text-mega" data-testid="correct">
            {correct}
          </p>
          <p data-copy="tam" className="m-0 mt-2 text-lead text-ink-soft">
            câu đúng
          </p>
        </Block>
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
