"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { forgetPendingSession, type PendingSession, readPendingSessions } from "@/lib/session-study/pending";

// F3 / CARDS-V3: while the cards of a finished session are being made, ask core-api now and then.
// The cards go straight into the Kho, so when the reading is done a toast says how many went in
// (or that there was nothing to make cards from, or that it failed: FIX-CHUNK, never in silence).
// Does nothing when no session is waiting.
const EVERY_MS = 5000;

type Result = { submission_status: string | null; cards: number };
type State = { kind: "waiting" } | { kind: "gone" } | { kind: "ready"; cards: number } | { kind: "failed" };

async function check(item: PendingSession): Promise<State> {
  try {
    const response = await fetch(`/api/sessions/${item.sessionId}/result`, { credentials: "same-origin" });
    if (response.status === 404 || response.status === 401) return { kind: "gone" };
    if (!response.ok) return { kind: "waiting" };
    const json = (await response.json()) as Result;
    if (json.submission_status === "failed") return { kind: "failed" };
    if (json.submission_status !== "done") return { kind: "waiting" };
    return { kind: "ready", cards: json.cards };
  } catch {
    return { kind: "waiting" };
  }
}

// cards: null when the session failed.
type Ready = PendingSession & { cards: number | null };

export function SessionReadyToast() {
  const [ready, setReady] = useState<Ready[]>([]);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      for (const item of readPendingSessions()) {
        const state = await check(item);
        if (stopped) return;
        if (state.kind === "waiting") continue;
        forgetPendingSession(item.sessionId);
        if (state.kind === "ready") setReady((rows) => [...rows, { ...item, cards: state.cards }]);
        if (state.kind === "failed") setReady((rows) => [...rows, { ...item, cards: null }]);
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
        <div key={item.sessionId} className="flex items-start gap-3 rounded-control border border-line bg-sunken p-4">
          {item.cards === null ? (
            <Link href={`/subjects/${item.subjectId}`} className="text-body inline-flex items-center justify-center min-h-11 rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
              Chưa tạo được thẻ cho buổi học môn {item.subject}. Mở môn để ghi lại buổi học.
            </Link>
          ) : item.cards > 0 ? (
            <Link href={`/kho-kien-thuc/${item.subjectId}`} className="text-body inline-flex items-center justify-center min-h-11 rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
              Đã thêm {item.cards} thẻ vào Kho cho buổi học môn {item.subject}
            </Link>
          ) : (
            <Link href={`/subjects/${item.subjectId}/syllabus`} className="text-body inline-flex items-center justify-center min-h-11 rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
              Chưa tìm thấy nội dung để làm thẻ cho buổi học môn {item.subject}. Chọn một mục từ đề cương.
            </Link>
          )}
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
