"use client";

import { useMemo } from "react";

import { createSessionApi } from "@/lib/session-study/api";
import type { DocRef } from "@/lib/session-study/mention";

import { SessionScreen, type SessionInitial } from "./session-screen";

// T7.12 (US-02, US-02b): the study session on core-api. The suggestion is the free session until
// the suggestion API reaches this screen (T7.13); the page tells which session this is.

const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn mục đề cương." } as const;

export function SessionLive({
  sessionId,
  subject,
  stopHref,
  docs,
  initial,
}: {
  sessionId: string;
  subject: string;
  stopHref: string;
  docs: DocRef[];
  initial: SessionInitial;
}) {
  const api = useMemo(() => createSessionApi(sessionId, docs), [sessionId, docs]);
  return (
    <SessionScreen
      api={api}
      subject={subject}
      stopHref={stopHref}
      docs={docs}
      suggestion={FREE}
      nextSuggestion={FREE}
      initial={initial}
    />
  );
}
