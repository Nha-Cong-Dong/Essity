"use client";

import { useEffect, useRef, useState } from "react";

import { StartButton } from "@/components/today/start-button";
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

const FULL = "max-sm:w-full";

function Suggested({ id, subjectId, subjectName, next }: { id: string; subjectId: string; subjectName: string; next: NextSuggestion }) {
  return (
    <>
      <h2 id={id} className="m-0 font-display text-lead wrap-anywhere">
        {next.label ? `Hôm nay nên học: mục ${next.label}` : "Hôm nay nên học"}
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
  preview = false,
  practiceLink = true,
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
  const learnedOut = shown.kind === "finished" || shown.kind === "exam_over";
  return (
    <Sheet variant="tile" className="flex min-w-0 flex-col gap-3" aria-labelledby={headingId} aria-busy={busy}>
      {computed && (
        <div ref={result} tabIndex={-1} aria-live="polite" className="flex flex-col gap-3 outline-none">
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
            <Button variant="secondary" onClick={ask} pending={busy} className={FULL}>
              {busy ? "Đang tính…" : "Gợi ý cho hôm nay"}
            </Button>
          </div>
          {failed && (
            <p role="alert" className="m-0 text-small">
              Chưa tính được gợi ý. Thử lại sau giây lát.
            </p>
          )}
        </>
      )}
      {shown.kind === "finished" && (
        <>
          <h2 id={headingId} className="m-0 text-read font-normal">
            {COPY.finished}
          </h2>
        </>
      )}
      {shown.kind === "exam_over" && (
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
      {shown.kind === "reading" && (
        <h2 id={headingId} role="status" className="m-0 text-read font-normal text-ink-soft">
          Đang đọc mục lục giáo trình…
        </h2>
      )}
      {showExtras && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3">
          <StartButton variant="secondary" subjectId={subjectId} preview={preview}>
            Ôn riêng môn này
          </StartButton>
          {learnedOut && practiceLink && (
            <Button render={<a href={`/subjects/${subjectId}/practice`} />} nativeButton={false} variant="quiet">
              {COPY.practice}
            </Button>
          )}
          {!noTextbook && shown.kind !== "exam_over" && (
            <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} variant="quiet">
              Học tự do
            </Button>
          )}
        </div>
      )}
    </Sheet>
  );
}
