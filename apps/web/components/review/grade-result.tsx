import type { ReactNode } from "react";

import { SourceQuote } from "@/components/review/source-quote";
import { VerdictChip, VerdictMark } from "@/components/review/verdict-chip";
import type { Result } from "@/lib/review-client";

// T2.16 (US-05 AC1, AC2, AC9; DESIGN.md §6.5, screens-html grading.html): the result column. The
// one deliberate motion of the app: its blocks rise one after another, then the pink band sweeps
// under the source (§3.5; reduced motion shows the end state). Nothing here asks the user to rate
// themselves (US-05 AC1). "Chấm sai" and "Bỏ câu này" come with T2.19.

/** The level of understanding, in pencil; hidden for a wrong or forgotten answer. */
const UNDERSTANDING: Record<number, string> = {
  1: "chỉ nhớ lại",
  2: "hiểu được vì sao",
  3: "vận dụng được",
};

/** A unit's verdict (US-05 AC9: "ý về độ trễ của UDP: thiếu"). */
const UNIT_LABEL: Record<Result["units"][number]["verdict"], string> = {
  correct: "Đúng",
  partial: "Một phần",
  incorrect: "Thiếu",
};

const STAGGER_MS = 60;

function Block({ order, children }: { order: number; children: ReactNode }) {
  return (
    <div className="mt-6.5 animate-rise first:mt-0" style={{ animationDelay: `${order * STAGGER_MS}ms` }}>
      {children}
    </div>
  );
}

function Pen({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="m-0 mb-1.5 font-hand text-body text-pencil">
      {children}
    </p>
  );
}

export function GradeResult({ result }: { result: Result }) {
  const understanding =
    result.overall === "correct" || result.overall === "partial"
      ? UNDERSTANDING[result.understanding ?? 0]
      : undefined;
  let order = 0;
  return (
    <div>
      <Block order={order++}>
        <p className="m-0 flex flex-wrap items-center gap-3">
          <VerdictChip verdict={result.overall} />
          {result.practice && (
            <span data-copy="tam" className="text-meta text-ink-soft">
              Chấm thử
            </span>
          )}
        </p>
        {understanding && <p className="m-0 mt-2.5 font-hand text-body text-pencil">{understanding}</p>}
      </Block>
      {result.missing.length > 0 && (
        <Block order={order++}>
          <Pen id="result-missing">còn thiếu</Pen>
          <ul aria-labelledby="result-missing" className="m-0 flex list-none flex-col gap-1.5 p-0">
            {result.missing.map((point) => (
              <li
                key={point}
                className="relative pl-5 wrap-anywhere before:absolute before:left-0 before:text-ink-soft before:content-['+']"
              >
                {point}
              </li>
            ))}
          </ul>
        </Block>
      )}
      {result.units.length > 1 && (
        <Block order={order++}>
          <Pen id="result-units">theo từng ý</Pen>
          <ul
            aria-labelledby="result-units"
            className="m-0 grid list-none grid-cols-1 gap-3 p-0 min-[901px]:grid-cols-2"
          >
            {result.units.map((unit) => (
              <li key={unit.unit_id} className="flex min-w-0 items-start gap-2.5 rounded-control bg-sunken px-3.5 py-3">
                <span className="mt-1.5">
                  <VerdictMark verdict={unit.verdict} />
                </span>
                <span className="min-w-0 wrap-anywhere">
                  {unit.title}
                  <span className="block text-meta text-ink-soft">{UNIT_LABEL[unit.verdict]}</span>
                </span>
              </li>
            ))}
          </ul>
        </Block>
      )}
      <Block order={order++}>
        <Pen>đáp án tham chiếu</Pen>
        <p className="m-0 text-read wrap-anywhere">{result.reference_answer}</p>
      </Block>
      {result.sources.length > 0 && (
        <Block order={order++}>
          <Pen>nguồn</Pen>
          <div className="flex flex-col gap-4">
            {result.sources.map((source) => (
              <SourceQuote key={source.anchor_id} source={source} />
            ))}
          </div>
        </Block>
      )}
    </div>
  );
}
