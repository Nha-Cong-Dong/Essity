import { Marker } from "@/components/notebook";
import { Sticker } from "@/components/motifs";
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

function Heading({ day }: { day: string }) {
  return (
    <div className="mb-8 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
      <h1 className="m-0 font-display text-title">
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
    item.kind === "review" ? reviewProgress(item.position, item.total) : draftLine(item.subject.name, item.drafts);
  const href = item.kind === "review" ? `/review/${item.session_id}` : `/subjects/${item.subject.id}/sessions`;
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

export function ReviewTile({ review, primary }: { review: TodayV2["review"]; primary: boolean }) {
  if (review.state === "none") {
    return (
      <Sheet
        variant="tile"
        tone="rose"
        className="flex min-h-48 min-w-0 flex-col justify-end gap-2 min-[901px]:col-span-8"
        aria-labelledby="today-review"
      >
        <h2 id="today-review" className="sr-only">
          {COPY.review}
        </h2>
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
      <p className="m-0 mt-auto flex items-baseline gap-3">
        <span className="font-display text-mega">{review.count}</span>
        <span className="text-lead">{COPY.questions}</span>
      </p>
      {/* A subject name may be one long word: it wraps, never widens the page. */}
      <p className="m-0 text-read wrap-anywhere">
        khoảng {review.minutes} phút · {review.subjects.join(", ")}
      </p>
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
          <StartButton variant={primary ? "primary-inverse" : "secondary"}>{COPY.start}</StartButton>
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
        className="relative flex min-h-80 min-w-0 flex-col gap-3 min-[901px]:col-span-8"
        aria-labelledby="today-review"
      >
        <Sticker icon="moon" className="top-7 right-8" />
        {body}
      </Sheet>
    );
  }
  return (
    <Sheet
      variant="tile"
      tone="rose"
      className="flex min-h-64 min-w-0 flex-col gap-3 min-[901px]:col-span-8"
      aria-labelledby="today-review"
    >
      {body}
    </Sheet>
  );
}

function LearnSection({ today, primary }: { today: TodayV2; primary: boolean }) {
  const { items, empty_reason } = today.learn;
  const first = items.findIndex((item) => item.state === "next");
  return (
    <Sheet variant="tile" className="min-w-0 min-[901px]:col-span-4" aria-labelledby="today-learn">
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
    </Sheet>
  );
}

function PracticeSection({ practice, primary }: { practice: NonNullable<TodayV2["practice"]>; primary: boolean }) {
  return (
    <Sheet variant="tile" className="min-w-0 min-[901px]:col-span-12" aria-labelledby="today-practice">
      <h2 id="today-practice" className="m-0 font-display text-lead">
        {COPY.practice}
      </h2>
      {practice.state === "none_ready" ? (
        <p className="m-0 mt-3 text-read text-ink-soft">
          {COPY.practiceNone}
        </p>
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

export function TodayV2Screen({ today }: { today: TodayV2 }) {
  if (today.subject_count === 0) {
    return (
      <>
        <Heading day={today.learning_day} />
        <section className="flex flex-col items-start gap-3 py-8" aria-labelledby="today-empty">
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
      <div className="grid gap-6 min-[901px]:grid-cols-12">
        {today.unfinished.length > 0 && <ResumeStrip items={today.unfinished} />}
        <ReviewTile review={today.review} primary={primary === "review"} />
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
      <div className="h-64 rounded-tile bg-sunken min-[901px]:col-span-8" />
      <div className="h-64 rounded-tile bg-sunken min-[901px]:col-span-4" />
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
