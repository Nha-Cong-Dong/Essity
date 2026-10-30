"use client";

import { CommandBar } from "@/components/command-bar";
import {
  type CommandState,
  EXAMPLE,
  fakeRun,
  fakeUndo,
  initialFor,
  PRACTICE_EXAMPLE,
  PRACTICE_EXHAUSTED,
  SUBJECT,
} from "@/lib/fixtures/command-bar";

// A mock subject screen header around the bar: the live subject layout is not touched (T9.3 does
// that). The bar answers from fixtures: "xóa…" is refused, "?" is unclear, anything else applies.

export function CommandPreview({ state }: { state: CommandState }) {
  const practice = state === "pending-ai-practice";
  return (
    <div className="mx-auto w-full max-w-280">
      <h1 className="m-0 font-display text-title [overflow-wrap:anywhere]">{practice ? "Luyện tập" : SUBJECT.name}</h1>
      <p className="mt-1 text-meta text-ink-soft">Môn học · 12 mục, 40 thẻ</p>
      <CommandBar
        key={state}
        example={practice ? PRACTICE_EXAMPLE : EXAMPLE}
        initial={initialFor(state)}
        exhaustedNote={practice ? PRACTICE_EXHAUSTED : undefined}
        run={async (command) => fakeRun(command.text)}
        undo={async () => fakeUndo()}
      />
      <section aria-label="Nội dung màn" className="rounded-sheet bg-sheet p-6 ring-1 ring-line">
        <p className="text-body text-ink-soft">Nội dung của màn môn nằm ở đây.</p>
      </section>
    </div>
  );
}
