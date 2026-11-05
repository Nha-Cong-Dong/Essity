"use client";

import { useState } from "react";

import { SessionScreen, type SessionInitial } from "@/components/session-study/session-screen";
import {
  DOCS,
  FILES,
  FREE_SUGGESTION,
  LONG_SUBJECT_NAME,
  NEXT_SUGGESTION,
  SCENARIOS,
  type Scenario,
  SUBJECT_NAME,
  SUGGESTION,
} from "@/lib/fixtures/session-study";
import type { Mention } from "@/lib/session-study/mention";
import { initialRound, type Round, type SessionResult } from "@/lib/session-study/round";

// T7.12a: the study session over typed fixtures. Each scenario is the state the screen starts in;
// "Trống" and "Học tự do" run on by themselves (a send ends in its cards after a moment).

const TEXT = "Tối nay mình học @Giáo trình phần 3.2 và xem lại @slide c3.";
const MENTIONS: Mention[] = [
  { docId: "d-textbook", name: "Giáo trình", start: 17, end: 28 },
  { docId: "d-slide", name: "slide c3", start: 48, end: 57 },
];

const DONE: SessionResult = { cards: 6, title: "TCP flow control", notice: null };
const at = (patch: Partial<Round>): Round => ({ ...initialRound, ...patch });

function initialFor(scenario: Scenario): SessionInitial {
  const base: SessionInitial = { round: initialRound, text: "", mentions: [], files: [] };
  const typed = { ...base, text: TEXT, mentions: MENTIONS };
  switch (scenario) {
    case "empty":
    case "free":
      return base;
    case "files":
      return { ...typed, files: FILES, tooManyPages: { total: 32, read: 20 } };
    case "refused":
      return { ...typed, round: at({ rejectedDoc: "d-textbook" }) };
    case "processing":
      return { ...typed, round: at({ phase: "processing", submission: "processing" }) };
    case "pending":
      return { ...typed, round: at({ phase: "processing", submission: "pending_ai" }) };
    case "failed":
      return { ...typed, round: at({ phase: "processing", submission: "failed" }) };
    case "done":
      return { ...typed, round: at({ phase: "done", result: DONE }) };
    case "done-none":
      return { ...typed, round: at({ phase: "done", result: { cards: 0, title: null, notice: "no_content_found" } }) };
  }
}

export function SessionPreview() {
  const [scenario, setScenario] = useState<Scenario>("empty");
  const [longName, setLongName] = useState(false);
  const free = scenario === "free";
  return (
    <>
      <nav aria-label="Trạng thái xem thử" className="border-b border-line bg-sunken px-4 py-3">
        <div className="mx-auto flex max-w-(--page-max) flex-wrap items-center gap-2 text-meta">
          <span className="text-ink-soft">Trạng thái:</span>
          {SCENARIOS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              aria-pressed={scenario === id}
              onClick={() => setScenario(id)}
              className="min-h-9 rounded-full px-3 inset-ring-[1.5px] inset-ring-line-strong aria-pressed:bg-ink aria-pressed:text-bg"
            >
              {label}
            </button>
          ))}
          <label className="ml-2 flex items-center gap-2">
            <input type="checkbox" checked={longName} onChange={(event) => setLongName(event.target.checked)} />
            Tên môn dài
          </label>
        </div>
      </nav>
      <SessionScreen
        key={`${scenario}-${longName}`}
        subject={longName ? LONG_SUBJECT_NAME : SUBJECT_NAME}
        stopHref="/design-preview"
        docs={DOCS}
        suggestion={free ? FREE_SUGGESTION : SUGGESTION}
        nextSuggestion={NEXT_SUGGESTION}
        initial={initialFor(scenario)}
        autoAdvance={scenario === "empty" || scenario === "free"}
        readResult={() => DONE}
      />
    </>
  );
}
