import type { Result } from "@/lib/review-client";

// T2.16 (design system v3.1 §4.6, DESIGN.md §6.5): the verdict as a pill on rose-50. A status
// colour never stands alone: each verdict has its own words and its own mark (full, half, hollow).

export type Verdict = Result["overall"];

export const VERDICT_LABEL: Record<Verdict, string> = {
  correct: "Đúng",
  partial: "Đúng một phần",
  incorrect: "Sai",
  forgot: "Không nhớ",
};

/** The 12px mark: full green, half yellow, hollow pencil. */
export function VerdictMark({ verdict }: { verdict: Verdict }) {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" className="size-3 shrink-0">
      {verdict === "correct" && <circle cx="6" cy="6" r="5.5" className="fill-correct" />}
      {verdict === "partial" && (
        <>
          <circle cx="6" cy="6" r="5" className="fill-none stroke-partial stroke-[1.5]" />
          <path d="M6 1 A5 5 0 0 0 6 11 Z" className="fill-partial" />
        </>
      )}
      {(verdict === "incorrect" || verdict === "forgot") && (
        <circle cx="6" cy="6" r="5" className="fill-none stroke-pencil stroke-[1.5]" />
      )}
    </svg>
  );
}

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  return (
    <span
      data-verdict={verdict}
      className="inline-flex h-7.5 items-center gap-2 rounded-full bg-rose-50 pr-3 pl-2.5 text-meta font-semibold whitespace-nowrap text-ink inset-ring-1 inset-ring-line"
    >
      <VerdictMark verdict={verdict} />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}
