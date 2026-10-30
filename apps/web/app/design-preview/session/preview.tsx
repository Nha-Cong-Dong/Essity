"use client";

import { useState } from "react";

import { SessionScreen, type SessionInitial } from "@/components/session-study/session-screen";
import {
  DOCS,
  DRAFTS,
  FILES,
  FREE_SUGGESTION,
  LONG_SUBJECT_NAME,
  MANY_DRAFTS,
  NEXT_SUGGESTION,
  SCENARIOS,
  type Scenario,
  SERVER_VERSION,
  SUBJECT_NAME,
  SUGGESTION,
} from "@/lib/fixtures/session-study";
import type { Mention } from "@/lib/session-study/mention";
import { initialRound, type Round } from "@/lib/session-study/round";

// T7.12a: the study session over typed fixtures. Each scenario is the state the screen starts in;
// "Trống" and "Học tự do" run on by themselves (a send ends in its cards after a moment).

const TEXT = "Tối nay mình học @Giáo trình mục 3.2 và xem lại @slide c3 tr. 10–14.";
const MENTIONS: Mention[] = [
  { docId: "d-textbook", name: "Giáo trình", start: 17, end: 28 },
  { docId: "d-slide", name: "slide c3", start: 48, end: 57 },
];
const SCOPE = [{ id: "s1", doc: "Giáo trình", from: 52, to: 58 }];

const at = (patch: Partial<Round>): Round => ({ ...initialRound, ...patch });

function initialFor(scenario: Scenario): SessionInitial {
  const base: SessionInitial = {
    round: initialRound,
    drafts: [],
    text: "",
    mentions: [],
    files: [],
    scope: [],
    saved: "section",
    resumed: false,
  };
  const review = { ...base, round: at({ phase: "review" }), text: TEXT, mentions: MENTIONS, scope: SCOPE };
  switch (scenario) {
    case "empty":
    case "free":
      return base;
    case "files":
      return { ...base, text: TEXT, mentions: MENTIONS, files: FILES, tooManyPages: { total: 32, read: 20 } };
    case "refused":
      return { ...base, text: TEXT, mentions: MENTIONS, round: at({ rejectedDoc: "d-textbook" }) };
    case "processing":
      return { ...base, text: TEXT, mentions: MENTIONS, round: at({ phase: "processing", submission: "processing" }) };
    case "pending":
      return { ...base, text: TEXT, mentions: MENTIONS, round: at({ phase: "processing", submission: "pending_ai" }) };
    case "failed":
      return { ...base, text: TEXT, mentions: MENTIONS, round: at({ phase: "processing", submission: "failed" }) };
    case "partial":
      return { ...review, drafts: DRAFTS, round: at({ phase: "review", partialNote: true }) };
    case "review":
      return { ...review, drafts: DRAFTS };
    case "conflict":
      return { ...review, drafts: DRAFTS.map((d, i) => (i === 0 ? { ...d, conflict: { mine: "Bên nhận báo cửa sổ nhận rwnd; bên gửi giữ dưới rwnd." } } : d)) };
    case "many":
      return { ...review, drafts: MANY_DRAFTS };
    case "empty-review":
      return review;
    case "save-error":
      return { ...review, drafts: DRAFTS, round: at({ phase: "review", saveError: true }) };
    case "saved":
      return { ...review, drafts: DRAFTS, round: at({ phase: "saved" }) };
    case "saved-partial":
      return { ...review, drafts: DRAFTS, round: at({ phase: "saved" }), saved: "partial" };
    case "saved-free":
      return { ...review, drafts: DRAFTS, round: at({ phase: "saved" }), mentions: [], text: "" };
    case "resume":
      return {
        ...review,
        resumed: true,
        drafts: DRAFTS.map((d, i) => (i === 1 ? { ...d, origin: "user" as const, summary: d.summary + " (đã sửa)" } : d)),
      };
  }
}

export function SessionPreview() {
  const [scenario, setScenario] = useState<Scenario>("empty");
  const [longName, setLongName] = useState(false);
  const free = scenario === "free" || scenario === "saved-free";
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
        readDrafts={() => DRAFTS}
        serverDraft={SERVER_VERSION}
      />
    </>
  );
}
