"use client";

import { type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

// T7.12a (DESIGN.md §6.7, design decisions C2, C5): the small pieces every area of the study
// session shares. Straight on the page background: the focus frame has no sheets (v3.1 §5).

/** One area of the round. Its heading takes focus after the user's own action (id `session-h-<phase>`). */
export function Region({
  phase,
  title,
  children,
  className,
}: {
  phase: string;
  title: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const heading = `session-h-${phase}`;
  return (
    <section aria-labelledby={heading} className={cn("flex flex-col gap-5 motion-safe:animate-rise", className)}>
      <h2 id={heading} tabIndex={-1} className="m-0 font-display text-lead outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** A finished area, folded to one line; a tap opens it again. */
export function DoneLine({ label, children }: { label: string; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-line pb-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex min-h-11 w-full items-center gap-2 rounded-control text-left text-meta text-ink-soft"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="shrink-0 text-correct">
          <path d="M2 6.5 5 9.5 10 3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="min-w-0 wrap-anywhere">{label}</span>
      </button>
      {open && children ? <div className="mt-2 text-body text-ink-soft wrap-anywhere">{children}</div> : null}
    </div>
  );
}

/** A notice box: sunken, with a 3px `--partial` rule on the left and a triangle. Never red. */
export function Notice({
  children,
  role,
  className,
}: {
  children: ReactNode;
  role?: "status" | "alert";
  className?: string;
}) {
  return (
    <div
      role={role}
      className={cn("flex gap-3 rounded-control border-l-[3px] border-partial bg-sunken p-4 text-body wrap-anywhere", className)}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="mt-1 shrink-0 text-partial">
        <path d="M8 1.75 14.5 13.5h-13z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M8 6.5v3.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r=".9" fill="currentColor" />
      </svg>
      <div className="flex min-w-0 flex-col items-start gap-3">{children}</div>
    </div>
  );
}

/** Long names are cut in the middle so the end ("…pptx") stays visible. */
export function MidTruncate({ text, tail = 10 }: { text: string; tail?: number }) {
  if (text.length <= tail * 2) return <span className="wrap-anywhere">{text}</span>;
  return (
    <span className="flex min-w-0" title={text}>
      <span className="truncate">{text.slice(0, -tail)}</span>
      <span className="shrink-0">{text.slice(-tail)}</span>
    </span>
  );
}
