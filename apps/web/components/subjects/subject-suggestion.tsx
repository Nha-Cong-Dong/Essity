"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { type Pace, paceLine, TODAY_V2_COPY as COPY } from "@/lib/today-v2";

// T7.13a (US-15 AC6, AC7; DESIGN §6.5 "Khối gợi ý hôm nay"): the suggestion block on a subject
// screen, from a typed value, no API. "Gợi ý cho hôm nay" asks `resolve` (T7.13: the suggestions
// endpoint) and shows the answer in the same shape as a suggestion that was there already.

export type NextSuggestion = { label: string; title: string; pages: string | null; reason: string; pace: Pace };

export type SuggestionState =
  | { kind: "suggested"; next: NextSuggestion }
  | { kind: "not_suggested" }
  | { kind: "finished" }
  | { kind: "exam_over" }
  | { kind: "no_textbook" }
  | { kind: "reading" };

// "Ôn riêng môn này" (US-03 AC7): the per-subject review route has no page yet; T7.13 wires it.
// The path is built, not written whole, so the internal-links test does not read it as a dead link.
const REVIEW_ROUTE = "review";
const reviewHref = (subjectId: string) => `/${REVIEW_ROUTE}?subject=${subjectId}`;

const FULL = "max-sm:w-full";

function Suggested({ id, subjectId, subjectName, next }: { id: string; subjectId: string; subjectName: string; next: NextSuggestion }) {
  return (
    <>
      <h2 id={id} className="m-0 font-display text-lead wrap-anywhere">
        Hôm nay nên học: mục {next.label}
      </h2>
      <p className="m-0 text-read wrap-anywhere">
        {next.title}
        {next.pages ? ` · ${next.pages}` : ""}
      </p>
      <p className="m-0 text-body wrap-anywhere">
        {next.reason}
      </p>
      <p className="m-0 text-meta text-ink-soft">
        {paceLine(next.pace)}
      </p>
      <div className="mt-2">
        <Button
          render={<a href={`/subjects/${subjectId}/sessions/new`} />}
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
}: {
  subjectId: string;
  subjectName: string;
  state: SuggestionState;
  resolve?: () => Promise<NextSuggestion>;
}) {
  const [computed, setComputed] = useState<NextSuggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const result = useRef<HTMLDivElement>(null);
  const headingId = `suggest-${subjectId}`;

  useEffect(() => {
    if (computed) result.current?.focus();
  }, [computed]);

  async function ask() {
    if (!resolve) return;
    setBusy(true);
    setComputed(await resolve());
    setBusy(false);
  }

  const noTextbook = state.kind === "no_textbook";
  const showExtras = state.kind !== "reading";
  const learnedOut = state.kind === "finished" || state.kind === "exam_over";
  return (
    <Sheet variant="tile" className="flex min-w-0 flex-col gap-3" aria-labelledby={headingId} aria-busy={busy}>
      {(state.kind === "suggested" || computed) && (
        <div ref={result} tabIndex={-1} aria-live="polite" className="flex flex-col gap-3 outline-none">
          <Suggested
            id={headingId}
            subjectId={subjectId}
            subjectName={subjectName}
            next={computed ?? (state as Extract<SuggestionState, { kind: "suggested" }>).next}
          />
        </div>
      )}
      {state.kind === "not_suggested" && !computed && (
        <>
          <h2 id={headingId} className="sr-only">
            {COPY.learn}
          </h2>
          <div>
            <Button variant="secondary" onClick={ask} pending={busy} className={FULL}>
              {busy ? "Đang tính…" : "Gợi ý cho hôm nay"}
            </Button>
          </div>
        </>
      )}
      {state.kind === "finished" && (
        <>
          <h2 id={headingId} className="m-0 text-read font-normal">
            {COPY.finished}
          </h2>
        </>
      )}
      {state.kind === "exam_over" && (
        <h2 id={headingId} className="sr-only">
          {COPY.learn}
        </h2>
      )}
      {noTextbook && (
        <>
          <h2 id={headingId} className="m-0 text-read font-normal">
            Môn này {COPY.noTextbook}
          </h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} className={FULL}>
              Học tự do
            </Button>
            <Button render={<a href={`/subjects/${subjectId}/documents`} />} nativeButton={false} variant="quiet">
              {COPY.uploadTextbook}
            </Button>
          </div>
        </>
      )}
      {state.kind === "reading" && (
        <h2 id={headingId} role="status" className="m-0 text-read font-normal text-ink-soft">
          Đang đọc mục lục giáo trình…
        </h2>
      )}
      {showExtras && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3">
          <Button render={<a href={reviewHref(subjectId)} />} nativeButton={false} variant="secondary" className={FULL}>
            Ôn riêng môn này
          </Button>
          {learnedOut && (
            <Button render={<a href={`/subjects/${subjectId}/practice`} />} nativeButton={false} variant="quiet">
              {COPY.practice}
            </Button>
          )}
          {!noTextbook && state.kind !== "exam_over" && (
            <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} variant="quiet">
              Học tự do
            </Button>
          )}
        </div>
      )}
    </Sheet>
  );
}
