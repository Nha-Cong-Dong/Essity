"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { go } from "@/lib/navigate";

// T2.14: "Bắt đầu" and "Ôn thêm" make (or find) today's session through web's
// POST /api/review-sessions, then go to it. A signed-out answer goes to /login.
export function StartButton({
  children,
  variant,
  "data-copy": copy,
  subjectId,
  preview = false,
  nothingDue = false,
}: {
  children: React.ReactNode;
  variant: "primary-inverse" | "secondary";
  /** "tam" while the label waits for the user's approval (R09). */
  "data-copy"?: "tam";
  /** "Ôn riêng môn này" (US-03 AC7): today's session for this subject only. */
  subjectId?: string;
  /** Design preview: the button is drawn but never calls the real API (T7.13). */
  preview?: boolean;
  /** T7.19 F3: the page already knows this subject has nothing due: say so, no button to press. */
  nothingDue?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [none, setNone] = useState(false);
  const empty = nothingDue || none;

  async function start() {
    if (preview) return;
    setPending(true);
    setFailed(false);
    try {
      const response = await fetch("/api/review-sessions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(subjectId === undefined ? {} : { subject_id: subjectId }),
      });
      if (response.status === 401) return go("/login");
      const body: unknown = response.ok ? await response.json() : null;
      const id = (body as { id?: unknown } | null)?.id;
      if (typeof id === "string") return go(`/review/${id}`);
      if (response.status === 409) {
        // Nothing due: for one subject say so here; for today's whole session /today says it.
        if (subjectId === undefined) return go("/today");
        setNone(true);
        setPending(false);
        return;
      }
    } catch {
      // network: say so below
    }
    setFailed(true);
    setPending(false);
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        type="button"
        variant={variant}
        size={variant === "secondary" ? "md" : "lg"}
        pending={pending}
        aria-disabled={empty || undefined}
        aria-describedby={empty ? "nothing-due" : undefined}
        className={empty ? "bg-sunken text-ink-soft inset-ring-line hover:bg-sunken" : undefined}
        onClick={empty ? undefined : start}
        data-copy={copy}
      >
        {children}
      </Button>
      {empty && (
        <p id="nothing-due" role="status" className="m-0 text-meta text-ink-soft">
          Môn này chưa có gì đến hạn ôn. Thẻ mới sẽ hiện khi đến hạn.
        </p>
      )}
      {failed && (
        <p role="alert" data-copy="tam" className="m-0 text-meta">
          Chưa mở được phiên. Thử lại sau giây lát.
        </p>
      )}
    </div>
  );
}
