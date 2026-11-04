import { Marker } from "@/components/notebook";
import { WeekStrip, type WeekCell } from "@/components/today-v2/week-strip";
import { LearnActions } from "@/components/today-v2/learn-actions";
import { Mascot } from "@/components/mascot";
import { NextStudyRow } from "@/components/today-v2/next-study-card";
import { StartButton } from "@/components/today/start-button";
import { Button } from "@/components/ui/button";
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
// V22: no card chrome except the one tinted sheet ("tờ chính") of the review; lists are rows.
const EDGE = "min-w-0";

function Heading({ day }: { day: string }) {
  return (
    <div className="mb-8 grid items-end gap-x-6 gap-y-2 min-[901px]:grid-cols-12">
      <h1 className="m-0 font-display text-title min-[901px]:col-span-8">
        <Marker>{COPY.heading}</Marker>
      </h1>
      <p className="m-0 text-body text-ink-soft min-[901px]:col-span-4 min-[901px]:justify-self-end">{dayLabel(day)}</p>
    </div>
  );
}

/** One row of Việc dở: the line, and "Tiếp tục" (primary on the first row only). */
function ResumeRow({ item, primary }: { item: Unfinished; primary: boolean }) {
  const variant = primary ? "primary" : "quiet";
  if (item.kind === "note") {
    return (
      <li className="m-0 text-small text-ink-soft break-words">
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
      <p className="m-0 min-w-0 flex-1 basis-60 text-read [overflow-wrap:anywhere]">
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
    <section className="min-w-0 border-b border-line pb-6 min-[901px]:col-span-12" aria-labelledby="today-unfinished">
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

// UI-A: the review is the answer of the screen: one tile (the page's one tint), the number at display
// size with Bé Trang beside it, the minutes, and the solid pink button at the foot. It is as tall as its
// neighbour ("Học gì tiếp"), so neither side has a hollow.
const REVIEW = "relative flex min-w-0 flex-col justify-between gap-6 rounded-tile bg-hong-tint p-4 min-[901px]:col-span-6 min-[901px]:p-6";

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
      <section className={REVIEW} data-surface="hong" aria-labelledby="today-review">
        <h2 id="today-review" className="m-0 font-display text-lead">
          {COPY.review}
        </h2>
        <div className="flex items-end justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <p className="m-0 font-display text-title">{COPY.nothingDue}</p>
            {review.next_due && <p className="m-0 text-body text-ink-soft">{nextDueLabel(review.next_due)}</p>}
          </div>
          <Mascot pose="vui" className="size-24 shrink-0 min-[901px]:size-32" />
        </div>
      </section>
    );
  }
  return (
    <section className={REVIEW} data-surface="hong" aria-labelledby="today-review">
      <h2 id="today-review" className="m-0 font-display text-lead">
        {COPY.review}
      </h2>
      <div className="flex flex-1 items-center justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="m-0 flex items-baseline gap-3">
            <span className="font-display text-display tabular-nums">{review.count}</span>
            <span className="text-lead font-semibold">{COPY.questions}</span>
          </p>
          {/* V5: the total only, no subject names. */}
          <p className="m-0 text-body text-ink-soft">khoảng {review.minutes} phút</p>
        </div>
        <Mascot pose="vui" className="size-24 shrink-0 min-[901px]:size-36" />
      </div>
      <div className="flex flex-col gap-3">
        {review.note && <p className="m-0 text-meta break-words">{review.note}</p>}
        {review.in_progress ? (
          <p className="m-0 text-meta">{COPY.inProgressHint}</p>
        ) : (
          <div className="max-sm:w-full">
            <StartButton variant={primary ? "primary" : "secondary"} preview={preview}>
              {COPY.start}
            </StartButton>
          </div>
        )}
      </div>
    </section>
  );
}

function LearnSection({ today, primary }: { today: TodayV2; primary: boolean }) {
  const { items, empty_reason } = today.learn;
  const first = items.findIndex((item) => item.state === "next");
  return (
    <section
      className={`${EDGE} flex flex-col gap-3.5 rounded-tile bg-hong-tint p-4 min-[901px]:col-span-6 min-[901px]:p-6`}
      aria-labelledby="today-learn"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="today-learn" className="m-0 font-display text-lead">
          {COPY.learn}
        </h2>
        {items.length > 0 ? <span className="text-meta italic text-ink-soft">Gợi ý, bạn chọn</span> : null}
      </div>
      {items.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {items.map((item, index) => (
            <NextStudyRow key={item.subject.id} item={item} next={index === first} />
          ))}
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
      <div className="mt-auto">
        <LearnActions items={items} primary={primary && first >= 0} />
      </div>
    </section>
  );
}

function PracticeSection({ practice, primary }: { practice: NonNullable<TodayV2["practice"]>; primary: boolean }) {
  return (
    <section className={`${EDGE} min-[901px]:col-span-6`} aria-labelledby="today-practice">
      <h2 id="today-practice" className="m-0 text-body font-semibold">
        {COPY.practice}
      </h2>
      {practice.state === "none_ready" ? (
        <div className="mt-3 flex items-center gap-4">
          <Mascot pose="cho" size="sm" />
          <p className="m-0 text-body text-ink-soft">{COPY.practiceNone}</p>
        </div>
      ) : (
        <ul className="m-0 mt-3 flex list-none flex-col gap-3 p-0">
          {practice.rows.map((row, index) => (
            <li key={row.subject_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className="m-0 min-w-0 flex-1 basis-40 text-body break-words">{practiceLine(row)}</p>
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
      <div className="grid gap-x-4 gap-y-8 min-[901px]:grid-cols-12 min-[901px]:gap-y-10">
        {today.unfinished.length > 0 && <ResumeStrip items={today.unfinished} />}
        <ReviewTile review={today.review} primary={primary === "review"} preview={preview} />
        <LearnSection today={today} primary={primary === "learn"} />
        {today.practice && <PracticeSection practice={today.practice} primary={primary === "practice"} />}
        {week && (
          <WeekStrip
            cells={week}
            today={today.learning_day}
            className={today.practice ? "min-[901px]:col-span-6" : "min-[901px]:col-span-12"}
          />
        )}
      </div>
    </>
  );
}

/** While the day loads: the shape of the four areas, never a page spinner. */
export function TodayV2Loading() {
  return (
    <div aria-busy="true" className="grid gap-6 min-[901px]:grid-cols-12">
      <div className="h-64 rounded-tile bg-hong-tint min-[901px]:col-span-6" />
      <div className="h-64 rounded-tile bg-hong-tint min-[901px]:col-span-6" />
      <div className="h-32 rounded-tile bg-hong-tint min-[901px]:col-span-12" />
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
