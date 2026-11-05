"use client";

import { useEffect, useRef, useState } from "react";

import { StartButton } from "@/components/today/start-button";
import { Button } from "@/components/ui/button";
import { FieldGrain } from "@/components/today-v2/field-art";
import { cn } from "@/lib/utils";
import { studyHref } from "@/lib/session-study/entry";
import { type Pace, paceLine, TODAY_V2_COPY as COPY } from "@/lib/today-v2";

// T7.13a (US-15 AC6, AC7; DESIGN §6.5 "Khối gợi ý hôm nay"): the suggestion block on a subject
// screen, from a typed value, no API. "Gợi ý cho hôm nay" asks `resolve` (T7.13: the suggestions
// endpoint) and shows the answer in the same shape as a suggestion that was there already.

export type NextSuggestion = { sectionId?: string | null; label: string; title: string; pages: string | null; reason: string; pace: Pace };

export type SuggestionState =
  | { kind: "suggested"; next: NextSuggestion }
  | { kind: "not_suggested" }
  | { kind: "finished" }
  | { kind: "rested" }
  | { kind: "exam_over" }
  | { kind: "no_textbook" }
  | { kind: "reading" };

const FULL = "max-sm:w-full";
// DESIGN-V4 (mockups subject-detail.html): this block is the screen's one field. Its buttons are pale pink
// (the on-plum action pair), its quiet buttons are outlined in the soft pink; --hong never sits on the field.
const ON_FIELD = "[--inverse-bg:var(--on-plum-action-bg)] [--inverse-fg:var(--on-plum-action-fg)]";
const QUIET_ON_FIELD = "border-0 bg-transparent text-on-plum inset-ring-on-plum-soft hover:bg-on-plum/10";

// The section to study is the title of the field: "Phần 3.2 Phân phối chuẩn", the page range and the pace under it.
function Suggested({ id, subjectId, subjectName, next }: { id: string; subjectId: string; subjectName: string; next: NextSuggestion }) {
  return (
    <>
      <h2 id={id} className="m-0 max-w-[16ch] font-display text-[clamp(32px,2.2vw+20px,50px)] leading-[1.02] font-semibold tracking-[-0.035em] break-words text-balance">
        {next.label ? `Phần ${next.label} ` : ""}
        {next.title}
      </h2>
      <p className="m-0 text-body text-on-plum-soft">
        Gợi ý cho hôm nay{next.pages ? ` · ${next.pages}` : ""} · {paceLine(next.pace)}
      </p>
      {next.reason ? <p className="m-0 text-meta text-on-plum-soft">{next.reason}</p> : null}
      <div className={cn("mt-1", ON_FIELD)}>
        <Button
          variant="primary-inverse"
          render={<a href={studyHref(subjectId, next.sectionId)} />}
          nativeButton={false}
          aria-label={`${COPY.enter} · ${subjectName}`}
          className={FULL}
        >
          {COPY.enter}
        </Button>
      </div>
    </>
  );
}

export function SubjectSuggestion({
  subjectId,
  subjectName,
  state,
  resolve,
  preview = false,
  practiceLink = true,
  nothingDue = false,
  reviewButton = true,
}: {
  subjectId: string;
  subjectName: string;
  state: SuggestionState;
  /** "Gợi ý cho hôm nay": the subject's suggestion now (T7.13: GET /api/subjects/{id}/suggestion). May throw. */
  resolve?: () => Promise<SuggestionState>;
  /** Design preview: "Ôn riêng môn này" never calls the real API. */
  preview?: boolean;
  /** The Luyện tập link: off until the practice screen exists (M8). */
  practiceLink?: boolean;
  /** T7.19 F3: today's review holds nothing of this subject. */
  nothingDue?: boolean;
  /** D6: the review button lives in the stack beside this block; the page turns it off here. */
  reviewButton?: boolean;
}) {
  const [answer, setAnswer] = useState<SuggestionState | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  // What the screen shows: the answer to the button once there is one, else what the page sent.
  const shown = answer ?? state;
  const computed = shown.kind === "suggested" ? shown.next : null;
  const result = useRef<HTMLDivElement>(null);
  const headingId = `suggest-${subjectId}`;

  useEffect(() => {
    if (answer && computed) result.current?.focus(); // only for an answer the learner asked for
  }, [answer, computed]);

  async function ask() {
    if (!resolve) return;
    setBusy(true);
    setFailed(false);
    try {
      setAnswer(await resolve());
    } catch {
      setFailed(true); // never stays on "Đang tính…": the button is back and says so
    }
    setBusy(false);
  }

  const noTextbook = shown.kind === "no_textbook";
  const showExtras = shown.kind !== "reading";
  const learnedOut = shown.kind === "finished" || shown.kind === "rested" || shown.kind === "exam_over";
  return (
    <section
      className="relative isolate flex min-h-60 min-w-0 flex-col justify-between gap-4 overflow-hidden rounded-tile bg-field p-6 text-on-plum min-[901px]:p-8"
      aria-labelledby={headingId}
      aria-busy={busy}
    >
      <FieldGrain />
      {computed && (
        <div ref={result} tabIndex={-1} aria-live="polite" className="flex flex-col items-start gap-3 outline-none">
          <Suggested
            id={headingId}
            subjectId={subjectId}
            subjectName={subjectName}
            next={computed}
          />
        </div>
      )}
      {shown.kind === "not_suggested" && (
        <>
          <h2 id={headingId} className="sr-only">
            {COPY.learn}
          </h2>
          <div>
            <Button variant="secondary" onClick={ask} pending={busy} className={cn(FULL, QUIET_ON_FIELD)}>
              {busy ? "Đang tính…" : "Gợi ý cho hôm nay"}
            </Button>
          </div>
          {failed && (
            <p role="alert" className="m-0 text-small text-on-plum-soft">
              Chưa tính được gợi ý. Thử lại sau giây lát.
            </p>
          )}
        </>
      )}
      {shown.kind === "finished" && (
        <>
          <h2 id={headingId} className="m-0 font-display text-lead">
            {COPY.finished}
          </h2>
        </>
      )}
      {shown.kind === "rested" && (
        <h2 id={headingId} className="m-0 font-display text-lead">
          {COPY.rested}
        </h2>
      )}
      {shown.kind === "exam_over" && (
        <h2 id={headingId} className="sr-only">
          {COPY.learn}
        </h2>
      )}
      {noTextbook && (
        <>
          <div className="flex min-w-0 flex-col gap-3">
            <h2 id={headingId} className="m-0 font-display text-[clamp(32px,2.2vw+20px,50px)] leading-[1.02] font-semibold tracking-[-0.035em] text-balance">
              Chưa có đề cương
            </h2>
            {/* SESSION-END: no outline, no study (core-api refuses too): the way on is the textbook. */}
            <p className="m-0 text-body text-on-plum-soft">Chưa học được: tải giáo trình chính để lập đề cương.</p>
          </div>
          <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1", ON_FIELD)}>
            <Button variant="primary-inverse" render={<a href={`/subjects/${subjectId}/documents`} />} nativeButton={false} className={FULL}>
              {COPY.uploadTextbook}
            </Button>
          </div>
        </>
      )}
      {shown.kind === "reading" && (
        <h2 id={headingId} role="status" className="m-0 text-body text-on-plum-soft">
          Đang đọc mục lục giáo trình…
        </h2>
      )}
      {showExtras && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-3">
          {reviewButton && (
            <StartButton variant="secondary" subjectId={subjectId} preview={preview} nothingDue={nothingDue}>
              Ôn riêng môn này
            </StartButton>
          )}
          {learnedOut && practiceLink && (
            <Button render={<a href={`/subjects/${subjectId}/practice`} />} nativeButton={false} variant="quiet" className={QUIET_ON_FIELD}>
              {COPY.practice}
            </Button>
          )}
          {!noTextbook && shown.kind !== "exam_over" && shown.kind !== "suggested" && (
            <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} variant="quiet" className={QUIET_ON_FIELD}>
              Học tự do môn này
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
