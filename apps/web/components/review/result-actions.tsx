"use client";

import { type ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AttemptView, ReviewApi } from "@/lib/review-client";

// T2.19 (US-09 AC1, AC3, AC4; DESIGN.md §6.5, screens-html grading.html): "Chấm sai" swaps in
// place for its one choice, "Bỏ câu này" is one tap; neither opens a dialog or asks again. The
// way on ("Câu tiếp") stays the one primary button throughout.

type Mode = "idle" | "choosing" | "updated" | "dropped";

export function ResultActions({
  gradeId,
  questionId,
  api,
  next,
  onOverridden,
}: {
  gradeId: string;
  questionId: string | null;
  api: ReviewApi;
  /** The screen's primary button, kept first in every mode. */
  next: ReactNode;
  onOverridden: (view: AttemptView) => void;
}) {
  const [mode, setMode] = useState<Mode>("idle");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function choose(verdict: "correct" | "incorrect") {
    setBusy(true);
    setFailed(false);
    const reply = await api.override(gradeId, verdict);
    setBusy(false);
    if (reply.ok) {
      setMode("updated");
      onOverridden(reply.data);
    } else {
      setFailed(true);
    }
  }

  async function drop() {
    if (!questionId) return;
    setBusy(true);
    setFailed(false);
    const reply = await api.drop(questionId);
    setBusy(false);
    if (reply.ok) setMode("dropped");
    else setFailed(true);
  }

  return (
    <>
      {mode === "updated" && (
        <p role="status" data-copy="tam" className="m-0 mt-7 rounded-control bg-sunken px-4 py-3 text-meta">
          Đã cập nhật kết quả và lịch ôn.
        </p>
      )}
      {mode === "dropped" && (
        <p role="status" data-copy="tam" className="m-0 mt-7 rounded-control bg-sunken px-4 py-3 text-meta">
          Câu này sẽ không xuất hiện lại.
        </p>
      )}
      {failed && (
        <p role="alert" data-copy="tam" className="m-0 mt-4 text-meta">
          Chưa gửi được. Bạn bấm lại nhé.
        </p>
      )}
      <div className="mt-9 flex flex-wrap items-center gap-2">
        {next}
        {mode === "choosing" ? (
          <>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void choose("correct")}>
              Thực ra tôi đúng
            </Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => void choose("incorrect")}>
              Thực ra tôi sai
            </Button>
          </>
        ) : (
          mode !== "dropped" && (
            <>
              <Button type="button" variant="quiet" disabled={busy} onClick={() => setMode("choosing")}>
                Chấm sai
              </Button>
              {questionId && (
                <Button type="button" variant="quiet" disabled={busy} onClick={() => void drop()}>
                  Bỏ câu này
                </Button>
              )}
            </>
          )
        )}
      </div>
    </>
  );
}
