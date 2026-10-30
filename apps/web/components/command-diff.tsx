import type { ReactNode } from "react";

import { type Diff, summarize } from "@/components/command/logic";

// T9.3a (US-18 AC1, AC4; DESIGN §6.14): one change as a sentence, "<lead> <what was done>.", and,
// when the change has an old and a new value, the pair "từ <cũ> thành <mới>" (read that way by a
// screen reader; the arrow is for the eye only). The count is already inside the sentence.

export function CommandDiff({
  lead,
  diff,
  id,
  trailing = ".",
}: {
  lead: string;
  diff: Diff;
  id?: string;
  trailing?: string;
}): ReactNode {
  return (
    <p id={id} className="min-w-0 text-body text-ink [overflow-wrap:anywhere]">
      <span>{lead} </span>
      <span data-user>{summarize(diff)}</span>
      {trailing}
      {diff.from !== undefined && diff.to !== undefined ? (
        <span data-diff className="mt-1 block">
          <span className="sr-only">từ </span>
          {/* Two lines each: a pasted paragraph must not take the screen; the full text is in the DOM. */}
          <span data-user className="line-clamp-2 text-ink-soft line-through decoration-line-strong">
            {diff.from}
          </span>
          <span aria-hidden="true" className="block">
            →
          </span>
          <span className="sr-only"> thành </span>
          <span data-user className="line-clamp-2 font-semibold">
            {diff.to}
          </span>
        </span>
      ) : null}
    </p>
  );
}
