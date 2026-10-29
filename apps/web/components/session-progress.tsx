"use client";

import { useEffect, useRef, useState } from "react";

import {
  fetchProgress,
  isEnd,
  MAX_FAILURES,
  nextDelay,
  type Progress,
  progressLine,
} from "@/lib/session-progress";

// T4.18 (US-02 AC11): what happens to a saved session, read from the server. Polls with a growing
// wait, stops at "done" or "failed", and says so once; leaving and coming back starts from the
// server's answer, not from anything remembered here.

export function SessionProgress({
  sessionId,
  onSignedOut,
  onDone,
}: {
  sessionId: string;
  onSignedOut?: () => void;
  onDone?: () => void;
}) {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [lost, setLost] = useState(false);
  // The callbacks may be new on every render: they must not restart the polling.
  const callbacks = useRef({ onSignedOut, onDone });
  useEffect(() => {
    callbacks.current = { onSignedOut, onDone };
  });

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let failures = 0;

    async function read() {
      const result = await fetchProgress(sessionId, abort.signal);
      if (abort.signal.aborted) return;
      if (result.ok) {
        failures = 0;
        setLost(false);
        setProgress(result.data);
        if (isEnd(result.data)) {
          if (result.data.state === "done") callbacks.current.onDone?.();
          return;
        }
      } else if (result.code === "signed_out") {
        return callbacks.current.onSignedOut?.();
      } else if (result.code === "session_not_found") {
        return setLost(true);
      } else if (++failures >= MAX_FAILURES) {
        return setLost(true); // a persistent 403/5xx or network error: stop, say so
      }
      timer = setTimeout(() => void read(), nextDelay(attempt++));
    }

    void read();
    return () => {
      abort.abort();
      if (timer) clearTimeout(timer);
    };
  }, [sessionId]);

  if (lost) {
    return (
      <p className="m-0 mt-4 text-read" data-copy="tam">
        Chưa xem được tiến trình. Tải lại trang để thử lại.
      </p>
    );
  }
  if (!progress) return <p className="m-0 mt-4 text-read text-ink-soft">…</p>;
  const percent = progress.state === "processing" ? progress.percent : null;
  return (
    <div className="mt-4" aria-live="polite">
      <p className="m-0 text-read" data-copy="tam">
        {progressLine(progress)}
      </p>
      {percent !== null && percent !== undefined && (
        <span className="progress mt-2 block h-2 w-full overflow-hidden rounded-full bg-sunken">
          <i
            className="block h-full bg-hong"
            style={{ width: `${percent}%` }}
            role="progressbar"
            aria-label="Tiến trình soạn câu hỏi"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </span>
      )}
    </div>
  );
}
