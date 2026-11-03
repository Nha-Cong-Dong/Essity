"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { forgetPendingSession, type PendingSession, readPendingSessions } from "@/lib/session-study/pending";

// F3: while the cards of a finished session are being made, ask core-api now and then. When the
// reading is done the drafts are saved as cards (the learner edits them in the knowledge store)
// and a toast says they are ready. Does nothing when no session is waiting.
const EVERY_MS = 5000;

type Draft = { id: string; version: number; status: string };

async function check(item: PendingSession): Promise<"ready" | "waiting" | "gone"> {
  try {
    const response = await fetch(`/api/sessions/${item.sessionId}/drafts`, { credentials: "same-origin" });
    if (response.status === 404 || response.status === 401) return "gone";
    if (!response.ok) return "waiting";
    const json = (await response.json()) as { submission_status: string | null; drafts: Draft[] };
    if (json.submission_status === "failed") return "gone";
    if (json.submission_status !== "done") return "waiting";
    const open = json.drafts.filter((d) => d.status === "draft");
    if (open.length > 0) {
      const saved = await fetch(`/api/sessions/${item.sessionId}/drafts/save`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ units: open.map((d) => ({ unit_id: d.id, version: d.version })) }),
      });
      if (!saved.ok) return "waiting";
    }
    return "ready";
  } catch {
    return "waiting";
  }
}

export function SessionReadyToast() {
  const [ready, setReady] = useState<PendingSession[]>([]);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      for (const item of readPendingSessions()) {
        const state = await check(item);
        if (stopped) return;
        if (state === "waiting") continue;
        forgetPendingSession(item.sessionId);
        if (state === "ready") setReady((rows) => [...rows, item]);
      }
    };
    const timer = window.setInterval(() => void tick(), EVERY_MS);
    void tick();
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  if (ready.length === 0) return null;
  return (
    <div className="fixed right-4 bottom-4 z-50 flex max-w-sm flex-col gap-2" role="status" aria-live="polite">
      {ready.map((item) => (
        <div key={item.sessionId} className="flex items-start gap-3 rounded-control border border-line bg-surface p-4 shadow-lg">
          <Link href={`/kho-kien-thuc/${item.subjectId}`} className="text-body underline underline-offset-4">
            Các thẻ của buổi học môn {item.subject} đã sẵn sàng
          </Link>
          <button
            type="button"
            aria-label="Đóng thông báo"
            className="min-h-11 min-w-11 text-ink-soft"
            onClick={() => setReady((rows) => rows.filter((r) => r.sessionId !== item.sessionId))}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
