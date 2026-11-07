"use client";

import { type ReactNode, useMemo } from "react";

import { createSessionApi } from "@/lib/session-study/api";
import type { Suggestion } from "@/lib/fixtures/session-study";
import type { DocRef } from "@/lib/session-study/mention";

import { SessionScreen, type SessionInitial } from "./session-screen";

// T7.12 (US-02, US-02b): the study session on core-api. A session opened from a suggestion shows
// its section (T7.19 F2); every other one is the free session.

const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;

export function SessionLive({
  sessionId,
  subjectId,
  subject,
  stopHref,
  docs,
  initial,
  suggestion = FREE,
  sectionId,
  stayOnComplete,
  account,
}: {
  sessionId: string;
  /** The subject the session belongs to (the way back; the "đã vào Kho" toast). */
  subjectId?: string;
  stayOnComplete?: boolean;
  subject: string;
  stopHref: string;
  docs: DocRef[];
  initial: SessionInitial;
  /** T7.19 F2: the section a suggestion opened this session for; none is the free session. */
  suggestion?: Suggestion;
  sectionId?: string;
  /** The account button of the app shell. */
  account?: ReactNode;
}) {
  const api = useMemo(() => createSessionApi(sessionId, docs, undefined, sectionId), [sessionId, docs, sectionId]);
  return (
    <SessionScreen
      api={api}
      account={account}
      subject={subject}
      subjectId={subjectId}
      stayOnComplete={stayOnComplete}
      stopHref={stopHref}
      docs={docs}
      suggestion={suggestion}
      nextSuggestion={FREE}
      initial={initial}
    />
  );
}
