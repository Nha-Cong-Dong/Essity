import { Button } from "@/components/ui/button";
import { type Card, pagesLine } from "@/lib/log-session";
import { dayLabel } from "@/lib/today-copy";

// T4.13a (US-02 AC4, DESIGN.md §6.10, screens-html log-session.html "Thẻ xác nhận"): the card
// says in words what the app understood; one press on Lưu if it is right, a sentence or the page
// range if it is not. The thumbnails of the first and last page wait for a page-image endpoint.

const BLOCK = "grid gap-1 border-t border-line py-4 first:border-t-0 first:pt-0";

function RangeBlock({ range }: { range: Card["ranges"][number] }) {
  const sections = range.sections.join(", ");
  const skim = range.depth === "skim";
  return (
    <div className={BLOCK}>
      <p className="m-0 text-meta text-ink-soft">{range.short_name}</p>
      <p className="m-0 text-read">{pagesLine(range.start_page, range.end_page)}</p>
      {(sections || skim) && (
        <p className="m-0 text-read">
          {sections}
          {sections && skim ? " · " : ""}
          {skim ? "đọc lướt" : ""}
        </p>
      )}
    </div>
  );
}

export type ConfirmCardProps = {
  card: Card;
  saving: boolean;
  /** Notes are still on their way to storage: Lưu waits for them. */
  waiting?: boolean;
  onSave: () => void;
  onSentence: () => void;
  onRanges: () => void;
};

export function ConfirmCard({ card, saving, waiting = false, onSave, onSentence, onRanges }: ConfirmCardProps) {
  const noteOnly = card.card === "note_only";
  return (
    <section aria-labelledby="confirm-lead" className="mt-6">
      <p id="confirm-lead" className="m-0 font-hand text-lead text-pencil">
        app hiểu như sau
      </p>
      <div className="mt-3">
        {noteOnly ? (
          <div className={BLOCK}>
            <p className="m-0 text-read" data-copy="tam">
              Buổi này không gắn với trang tài liệu nào.
            </p>
          </div>
        ) : (
          card.ranges.map((range) => (
            <RangeBlock key={`${range.document_id}-${range.start_page}-${range.end_page}`} range={range} />
          ))
        )}
        <div className={BLOCK}>
          <p className="m-0 text-meta text-ink-soft">Ngày học</p>
          <p className="m-0 text-read">{card.studied_on ? dayLabel(card.studied_on) : "hôm nay"}</p>
        </div>
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button type="button" pending={saving} disabled={waiting} onClick={onSave}>
          Lưu
        </Button>
        <Button type="button" variant="quiet" disabled={saving} onClick={onSentence}>
          Sửa bằng một câu
        </Button>
        {!noteOnly && (
          <Button type="button" variant="quiet" disabled={saving} onClick={onRanges}>
            Chỉnh khoảng trang
          </Button>
        )}
      </div>
    </section>
  );
}
