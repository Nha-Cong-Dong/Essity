import { Marker } from "@/components/notebook";
import { LearnActions } from "@/components/today-v2/learn-actions";
import { Mascot } from "@/components/mascot";
import { NextStudyCard } from "@/components/today-v2/next-study-card";
import { StartButton } from "@/components/today/start-button";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { dayLabel } from "@/lib/today-copy";
import {
  draftLine,
  nextDueLabel,
  practiceLine,
  primaryAction,
  reviewProgress,
  TODAY_V2_COPY as COPY,
  type TodayV2,
  type Unfinished,
} from "@/lib/today-v2";

// T7.13a (US-03, US-15, DESIGN §6.2, design-decisions.md): Hôm nay v2 from a typed value, no API.
// Order: Việc dở, Ôn hôm nay, Học gì tiếp, Luyện tập. Exactly one primary button per state.

const FULL = "max-sm:w-full";
// Phase B: a quiet card with the landing's thin pink top edge (a border, so no shadow).
const EDGE = "min-w-0 border border-line border-t-4 border-t-hong shadow-none hover:shadow-none";

function Heading({ day }: { day: string }) {
  return (
    <div className="mb-10 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
      <h1 className="m-0 font-display text-display">
        <Marker>{COPY.heading}</Marker>
      </h1>
      <p className="m-0 text-read text-ink-soft">{dayLabel(day)}</p>
    </div>
  );
}

/** One row of Việc dở: the line, and "Tiếp tục" (primary on the first row only). */
function ResumeRow({ item, primary }: { item: Unfinished; primary: boolean }) {
  const variant = primary ? "primary" : "secondary";
  if (item.kind === "note") {
    return (
      <li className="m-0 text-small text-ink-soft wrap-anywhere">
        {item.text}
      </li>
    );
  }
  const line =
    item.kind === "review"
      ? reviewProgress(item.position, item.total)
      : item.kind === "session"
        ? item.line
        : draftLine(item.subject.name, item.drafts);
  const href =
    item.kind === "review"
      ? `/review/${item.session_id}`
      : item.kind === "session"
        ? `/subjects/${item.subject.id}/sessions/${item.session_id}`
        : `/subjects/${item.subject.id}/sessions`;
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
      <p className="m-0 min-w-0 flex-1 basis-60 text-read wrap-anywhere">
        {line}
      </p>
      <Button
        render={<a href={href} />}
        nativeButton={false}
        variant={variant}
        aria-label={item.kind === "review" ? undefined : `${COPY.resume} · ${item.subject.name}`}
        className={FULL}
      >
        {COPY.resume}
      </Button>
    </li>
  );
}

export function ResumeStrip({ items }: { items: Unfinished[] }) {
  const first = items.findIndex((item) => item.kind !== "note");
  return (
    <Sheet variant="sunken" className="min-w-0 min-[901px]:col-span-12" aria-labelledby="today-unfinished">
      <h2 id="today-unfinished" className="m-0 mb-3 font-display text-lead">
        {COPY.unfinished}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {items.map((item, index) => {
          return <ResumeRow key={index} item={item} primary={index === first} />;
        })}
      </ul>
    </Sheet>
  );
}

export function ReviewTile({
  review,
  primary,
  preview = false,
}: {
  review: TodayV2["review"];
  primary: boolean;
  preview?: boolean;
}) {
  if (review.state === "none") {
    return (
      <Sheet
        variant="tile"
        tone="rose"
        className="flex min-w-0 flex-col gap-2 self-start min-[901px]:col-span-7"
        aria-labelledby="today-review"
      >
        <h2 id="today-review" className="sr-only">
          {COPY.review}
        </h2>
        <Mascot pose="vui" />
        <p className="m-0 font-display text-lead">
          {COPY.nothingDue}
        </p>
        {review.next_due && (
          <p className="m-0 text-read text-ink-soft">
            {nextDueLabel(review.next_due)}
          </p>
        )}
      </Sheet>
    );
  }
  const body = (
    <>
      <h2 id="today-review" className="m-0 text-read font-normal">
        {COPY.review}
      </h2>
      <p className="m-0 flex items-baseline gap-3">
        <span className="font-display text-display tabular-nums">{review.count}</span>
        <span className="text-lead">{COPY.questions}</span>
      </p>
      {/* V5: the total only, no subject names. */}
      <p className="m-0 text-read">khoảng {review.minutes} phút</p>
      {review.note && (
        <p className="m-0 text-small wrap-anywhere">
          {review.note}
        </p>
      )}
      {review.in_progress ? (
        <p className="m-0 text-small">
          {COPY.inProgressHint}
        </p>
      ) : (
        <div className="mt-4">
          <StartButton variant={primary ? "primary-inverse" : "secondary"} preview={preview}>
            {COPY.start}
          </StartButton>
        </div>
      )}
    </>
  );
  // One pink tile, only when it carries the primary button (design-decisions #2).
  if (primary) {
    return (
      <Sheet
        variant="tile"
        tone="hong"
        className="relative flex min-w-0 flex-col gap-3 self-start min-[901px]:col-span-7"
        aria-labelledby="today-review"
      >
        <Mascot pose="vui" className="absolute top-6 right-6 max-sm:size-20" />
        {body}
      </Sheet>
    );
  }
  return (
    <Sheet
      variant="tile"
      tone="rose"
      className="relative flex min-w-0 flex-col gap-3 self-start min-[901px]:col-span-7"
      aria-labelledby="today-review"
    >
      <Mascot pose="vui" className="absolute top-6 right-6 max-sm:size-20" />
      {body}
    </Sheet>
  );
}

function LearnSection({ today, primary }: { today: TodayV2; primary: boolean }) {
  const { items, empty_reason } = today.learn;
  const first = items.findIndex((item) => item.state === "next");
  return (
    <Sheet variant="tile" className={`${EDGE} min-[901px]:col-span-5`} aria-labelledby="today-learn">
      <h2 id="today-learn" className="m-0 font-display text-lead">
        {COPY.learn}
      </h2>
      {items.length > 0 ? (
        <ul className="m-0 mt-4 flex list-none flex-col gap-6 p-0">
          {items.map((item, index) => (
            <li key={item.subject.id}>
              <NextStudyCard item={item} primary={primary && index === first} />
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-3 flex flex-col items-start gap-1">
          <p className="m-0 text-read">
            {empty_reason ? COPY.emptyReason[empty_reason] : COPY.emptyReason.no_textbook}
          </p>
          <nav aria-label={COPY.learn} className="-ml-3 flex flex-wrap">
            <Button render={<a href="/subjects" />} nativeButton={false} variant="quiet">
              {COPY.subjects}
            </Button>
          </nav>
        </div>
      )}
      <LearnActions items={items} primary={primary && first >= 0} />
    </Sheet>
  );
}

function PracticeSection({ practice, primary }: { practice: NonNullable<TodayV2["practice"]>; primary: boolean }) {
  return (
    <Sheet variant="tile" className={`${EDGE} min-[901px]:col-span-12`} aria-labelledby="today-practice">
      <h2 id="today-practice" className="m-0 font-display text-lead">
        {COPY.practice}
      </h2>
      {practice.state === "none_ready" ? (
        <div className="mt-3 flex items-center gap-4">
          <Mascot pose="cho" size="sm" />
          <p className="m-0 text-read text-ink-soft">{COPY.practiceNone}</p>
        </div>
      ) : (
        <ul className="m-0 mt-4 flex list-none flex-col gap-4 p-0">
          {practice.rows.map((row, index) => (
            <li key={row.subject_id} className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2">
              <p className="m-0 min-w-0 flex-1 basis-60 text-read wrap-anywhere">
                {practiceLine(row)}
              </p>
              <Button
                render={<a href={`/subjects/${row.subject_id}/practice`} />}
                nativeButton={false}
                variant={primary && index === 0 ? "primary" : "quiet"}
                aria-label={`${COPY.openPractice} · ${row.name}`}
                className={primary && index === 0 ? FULL : undefined}
              >
                {COPY.openPractice}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  );
}

/** `preview`: the design-preview routes draw the screen but its buttons never call the API. */
export function TodayV2Screen({ today, preview = false }: { today: TodayV2; preview?: boolean }) {
  if (today.subject_count === 0) {
    return (
      <>
        <Heading day={today.learning_day} />
        <section className="flex flex-col items-start gap-3 py-8" aria-labelledby="today-empty">
          <Mascot pose="vui" size="lg" />
          <p id="today-empty" className="m-0 font-display text-title">
            {COPY.noSubjects}
          </p>
          <p className="m-0 text-read text-ink-soft">{COPY.noSubjectsHint}</p>
          <Button render={<a href="/subjects/new" />} nativeButton={false} className={`mt-3 ${FULL}`}>
            {COPY.createSubject}
          </Button>
        </section>
      </>
    );
  }
  const primary = primaryAction(today);
  return (
    <>
      <Heading day={today.learning_day} />
      <div data-reveal className="grid gap-8 min-[901px]:grid-cols-12">
        {today.unfinished.length > 0 && <ResumeStrip items={today.unfinished} />}
        <ReviewTile review={today.review} primary={primary === "review"} preview={preview} />
        <LearnSection today={today} primary={primary === "learn"} />
        {today.practice && <PracticeSection practice={today.practice} primary={primary === "practice"} />}
      </div>
    </>
  );
}

/** While the day loads: the shape of the four areas, never a page spinner. */
export function TodayV2Loading() {
  return (
    <div aria-busy="true" className="grid gap-6 min-[901px]:grid-cols-12">
      <div className="h-24 rounded-sheet bg-sunken min-[901px]:col-span-12" />
      <div className="h-64 rounded-tile bg-sunken min-[901px]:col-span-7" />
      <div className="h-64 rounded-tile bg-sunken min-[901px]:col-span-5" />
      <div className="h-32 rounded-tile bg-sunken min-[901px]:col-span-12" />
      <p className="sr-only" role="status">
        {COPY.loading}
      </p>
    </div>
  );
}

export function TodayV2Failed() {
  return (
    <div role="alert" className="flex max-w-160 flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
      <p className="m-0">
        <b>{COPY.failed}</b> {COPY.failedHint}
      </p>
      <Button render={<a href="/today" />} nativeButton={false} variant="secondary" className="mt-3">
        {COPY.retry}
      </Button>
    </div>
  );
}
