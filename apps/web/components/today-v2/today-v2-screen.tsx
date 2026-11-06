import { FieldGrain, StarSticker } from "@/components/today-v2/field-art";
import { WeekStrip, type WeekCell } from "@/components/today-v2/week-strip";
import { LearnActions } from "@/components/today-v2/learn-actions";
import { Mascot } from "@/components/mascot";
import { NextStudyRow } from "@/components/today-v2/next-study-card";
import { StartButton } from "@/components/today/start-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { dayLabel } from "@/lib/today-copy";
import {
  nextDueLabel,
  practiceLine,
  primaryAction,
  reviewProgress,
  TODAY_V2_COPY as COPY,
  type TodayV2,
  type Unfinished,
} from "@/lib/today-v2";

// DESIGN-V4 (mockups today.html, 06/11): Hôm nay v2 from a typed value, no API. Desktop: the left column
// holds "Học gì tiếp theo?" and "Luyện tập" as white sheets; the right column is ONE field poster, "Ôn hôm
// nay" over "Tuần này". On a phone the poster splits and the order is Học gì tiếp, Ôn, Luyện tập, Tuần này.
// Việc dở, when there is any, is a thin sheet on top. Exactly one primary button per state.

const FULL = "max-sm:w-full";
// A white sheet on the page ground: a hairline and the soft app shadow (elev-1), never a tint on the ground.
const SHEET = "min-w-0 rounded-tile bg-sheet p-6 shadow-sheet";
// The field's primary button: pale pink on the field (the on-plum action pair), never --hong on it.
const ON_FIELD = "[--inverse-bg:var(--on-plum-action-bg)] [--inverse-fg:var(--on-plum-action-fg)]";

function Heading({ day }: { day: string }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <h1 className="m-0 font-display text-title">{COPY.heading}</h1>
      <p className="m-0 text-body text-ink-soft">{dayLabel(day)}</p>
    </div>
  );
}

/** One row of Việc dở: the line, and "Tiếp tục" (primary on the first row only). */
function ResumeRow({ item, primary }: { item: Unfinished; primary: boolean }) {
  const variant = primary ? "primary" : "quiet";
  if (item.kind === "note") {
    return <li className="m-0 text-small text-ink-soft break-words">{item.text}</li>;
  }
  const line = item.kind === "review" ? reviewProgress(item.position, item.total) : item.line;
  const href =
    item.kind === "review" ? `/review/${item.session_id}` : `/subjects/${item.subject.id}/sessions/${item.session_id}`;
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-5 gap-y-3">
      <p className="m-0 min-w-0 flex-1 basis-60 text-read [overflow-wrap:anywhere]">{line}</p>
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
    <section className={cn(SHEET, "py-4 min-[1024px]:col-span-12")} aria-labelledby="today-unfinished">
      <h2 id="today-unfinished" className="m-0 mb-3 text-body font-semibold">
        {COPY.unfinished}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {items.map((item, index) => {
          return <ResumeRow key={index} item={item} primary={index === first} />;
        })}
      </ul>
    </section>
  );
}

// The review is the answer of the screen: the top half of the field poster (rounded all round on a phone,
// open at the bottom from 1024px where "Tuần này" continues it). The star sits top right and the text
// keeps clear of it (the done title is at least 40px from it).
const REVIEW =
  "relative isolate flex flex-col gap-5 overflow-hidden rounded-tile bg-field p-6 text-on-plum min-[1024px]:p-8 max-[1023px]:order-2";
// With "Tuần này" under it the review is open at the bottom, so the two read as one poster.
const JOINED = "min-[1024px]:[border-bottom-left-radius:0] min-[1024px]:[border-bottom-right-radius:0] min-[1024px]:pb-5";

export function ReviewTile({
  review,
  primary,
  preview = false,
  joined = false,
}: {
  review: TodayV2["review"];
  primary: boolean;
  preview?: boolean;
  /** "Tuần này" continues the field under this block (desktop). */
  joined?: boolean;
}) {
  if (review.state === "none") {
    return (
      <section className={cn(REVIEW, joined && JOINED)} aria-labelledby="today-review">
        <FieldGrain />
        <StarSticker className="top-4 right-6 size-22 max-[1023px]:size-15">
          <svg viewBox="0 0 24 24" aria-hidden="true" className="relative size-7 -rotate-8 stroke-field" fill="none" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </StarSticker>
        <h2 id="today-review" className="m-0 font-display text-lead">
          {COPY.review}
        </h2>
        <div className="flex min-w-0 flex-col gap-3">
          <p className="m-0 mt-3 max-w-[min(12ch,calc(100%-8.5rem))] font-display text-title leading-[1.05]">{COPY.nothingDue}</p>
          {review.next_due && <p className="m-0 text-body text-on-plum-soft">{nextDueLabel(review.next_due)}</p>}
        </div>
      </section>
    );
  }
  return (
    <section className={cn(REVIEW, joined && JOINED)} aria-labelledby="today-review">
      <FieldGrain />
      <StarSticker className="top-5 right-6 size-21 max-[1023px]:size-15" />
      <h2 id="today-review" className="m-0 font-display text-lead">
        {COPY.review}
      </h2>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="m-0 flex items-baseline gap-3">
          <span className="font-display text-display leading-none font-semibold tracking-[-0.05em] tabular-nums">{review.count}</span>
          <span className="text-lead font-semibold">{COPY.questions}</span>
        </p>
        {/* V5: the total only, no subject names. */}
        <p className="m-0 mt-2 text-body text-on-plum-soft">khoảng {review.minutes} phút</p>
      </div>
      <div className="flex flex-col gap-3">
        {review.note && <p className="m-0 text-meta break-words text-on-plum-soft">{review.note}</p>}
        {review.in_progress ? (
          <p className="m-0 text-meta text-on-plum-soft">{COPY.inProgressHint}</p>
        ) : (
          <div className={cn("max-sm:w-full", ON_FIELD)}>
            <StartButton variant={primary ? "primary-inverse" : "secondary"} preview={preview}>
              {COPY.start}
            </StartButton>
          </div>
        )}
      </div>
    </section>
  );
}

// UI-A (user 05/11): the box shows only the top-priority subject; "Xem tất cả" opens the full list.
// Unchanged in structure and words; v4 only moves it onto a white sheet with a quiet block row.
function LearnSection({ today, primary }: { today: TodayV2; primary: boolean }) {
  const { items, empty_reason } = today.learn;
  const first = items.findIndex((item) => item.state === "next");
  return (
    <section className={cn(SHEET, "flex flex-col gap-3.5 max-[1023px]:order-1")} aria-labelledby="today-learn">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="today-learn" className="m-0 font-display text-tile">
          {COPY.learn}
        </h2>
        {items.length > 0 ? <span className="text-meta italic text-ink-soft">Gợi ý, bạn chọn</span> : null}
      </div>
      {items.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          <NextStudyRow key={items[Math.max(first, 0)].subject.id} item={items[Math.max(first, 0)]} next={first >= 0} />
        </ul>
      ) : (
        <div className="flex flex-col items-start gap-1">
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
      <div>
        <LearnActions items={items} primary={primary && first >= 0} />
      </div>
    </section>
  );
}

function PracticeSection({ practice, primary }: { practice: NonNullable<TodayV2["practice"]>; primary: boolean }) {
  return (
    <section className={cn(SHEET, "max-[1023px]:order-3")} aria-labelledby="today-practice">
      <h2 id="today-practice" className="m-0 font-display text-tile">
        {COPY.practice}
      </h2>
      {practice.state === "none_ready" ? (
        <div className="mt-3 flex items-center gap-4">
          <Mascot pose="cho" size="sm" />
          <p className="m-0 text-body text-ink-soft">{COPY.practiceNone}</p>
        </div>
      ) : (
        <ul className="m-0 mt-3 flex list-none flex-col p-0">
          {practice.rows.map((row, index) => (
            <li
              key={row.subject_id}
              className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-t border-line py-3.5 first:border-t-0 first:pt-1 max-[520px]:flex-col max-[520px]:items-stretch"
            >
              <p className="m-0 min-w-0 flex-1 basis-40 text-body [overflow-wrap:anywhere]">{practiceLine(row)}</p>
              <Button
                render={<a href={`/subjects/${row.subject_id}/practice`} />}
                nativeButton={false}
                variant={primary && index === 0 ? "primary" : "quiet"}
                aria-label={`${COPY.openPractice} · ${row.name}`}
                className={primary && index === 0 ? FULL : "max-[520px]:w-full"}
              >
                {COPY.openPractice}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** `preview`: the design-preview routes draw the screen but its buttons never call the API. */
export function TodayV2Screen({
  today,
  preview = false,
  week,
}: {
  today: TodayV2;
  preview?: boolean;
  week?: WeekCell[];
}) {
  if (today.subject_count === 0) {
    return (
      <>
        <Heading day={today.learning_day} />
        <section className="flex flex-col items-start gap-3 py-8" aria-labelledby="today-empty">
          <Mascot pose="rong" size="lg" />
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
      <div className="grid gap-5 min-[1024px]:grid-cols-12 min-[1024px]:items-start">
        {today.unfinished.length > 0 && <ResumeStrip items={today.unfinished} />}
        {/* Left column: from 1024px two stacked sheets; on a phone its children join the page order. */}
        <div className="flex min-w-0 flex-col gap-5 max-[1023px]:contents min-[1024px]:col-span-7">
          <LearnSection today={today} primary={primary === "learn"} />
          {today.practice && <PracticeSection practice={today.practice} primary={primary === "practice"} />}
        </div>
        {/* Right column: the field poster (review over week) from 1024px; split on a phone. */}
        <div className="flex min-w-0 flex-col max-[1023px]:contents min-[1024px]:col-span-5">
          <ReviewTile review={today.review} primary={primary === "review"} preview={preview} joined={Boolean(week)} />
          {week && <WeekStrip cells={week} today={today.learning_day} className="max-[1023px]:order-4" />}
        </div>
      </div>
    </>
  );
}

/** While the day loads: the shape of the areas, never a page spinner. */
export function TodayV2Loading() {
  return (
    <div aria-busy="true" className="grid gap-5 min-[1024px]:grid-cols-12">
      <div className="h-64 rounded-tile bg-sunken min-[1024px]:col-span-7" />
      <div className="h-64 rounded-tile bg-sunken min-[1024px]:col-span-5" />
      <div className="h-40 rounded-tile bg-sunken min-[1024px]:col-span-7" />
      <p className="sr-only" role="status">
        {COPY.loading}
      </p>
    </div>
  );
}

export function TodayV2Failed() {
  return (
    <div role="alert" className="flex max-w-160 flex-col items-start gap-2 rounded-tile bg-sunken p-6">
      <p className="m-0">
        <b>{COPY.failed}</b> {COPY.failedHint}
      </p>
      <Button render={<a href="/today" />} nativeButton={false} variant="secondary" className="mt-3">
        {COPY.retry}
      </Button>
    </div>
  );
}
