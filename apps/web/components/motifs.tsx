import type { ReactNode } from "react";
import { Moon, Paperclip, PenLine, Sparkle } from "lucide-react";

import { cn } from "@/lib/utils";

// Motifs of design system v3.1 §4.10: decoration only, never information. Always aria-hidden,
// never behind text, at most three kinds on a screen, none on the answering screen. They drift
// slowly (motif-float) and stand still when motion is reduced. Styles live in app/globals.css.

/** M1: a 24px grid fading from one corner of the nearest positioned box. Hidden ≤ 900px. */
export function GridCorner({ corner, className }: { corner: "tl" | "tr" | "bl" | "br"; className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-motif="grid"
      className={cn("motif motif-grid motif-wide motif-float", corner, className)}
    />
  );
}

const ICONS = { moon: Moon, pen: PenLine, paperclip: Paperclip, sparkle: Sparkle } as const;

/** M8: one sticker per screen, tilted, with a ring of the surface under it. */
export function Sticker({
  icon,
  className,
}: {
  icon: keyof typeof ICONS;
  className?: string;
}) {
  const Icon = ICONS[icon];
  return (
    <span aria-hidden="true" data-motif="sticker" className={cn("sticker motif-float slow", className)}>
      <Icon aria-hidden="true" focusable="false" strokeWidth={1.9} />
    </span>
  );
}

/** V21 note sticker: a short word on a highlighter tag, tilted 8°, ring of the card under it. One per screen. */
export function NoteSticker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-motif="note-sticker"
      className={cn(
        "pointer-events-none absolute -top-3.5 right-4 z-1 rotate-[8deg] rounded-slip bg-hl px-3 py-1.5 text-meta font-semibold text-ink shadow-[0_0_0_4px_var(--sheet)]",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** V21 M-margin: the pink margin rule of a notebook page. Put it inside a `relative` card with `pl-11`. */
export function MarginRule({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-motif="margin"
      className={cn("pointer-events-none absolute inset-y-0 left-[30px] w-0.5 bg-rose-300", className)}
    />
  );
}

/**
 * V21 watermark: a big faint ring of dots with one highlighter stroke, in the bottom-right corner of
 * the nearest positioned box. Decoration only; behind the content, hidden on phones.
 */
export function Watermark({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-motif="watermark"
      viewBox="0 0 520 520"
      className={cn(
        "pointer-events-none absolute -right-16 -bottom-10 z-0 size-[520px] opacity-40 max-[900px]:hidden",
        className,
      )}
    >
      {Array.from({ length: 36 }, (_, k) => {
        const a = (k / 36) * Math.PI * 2;
        return <circle key={k} cx={260 + 200 * Math.cos(a)} cy={260 + 200 * Math.sin(a)} r={5} fill="var(--motif-grid)" />;
      })}
      <path d="M120 360 C220 300 320 420 420 340" fill="none" stroke="var(--hl)" strokeWidth={18} strokeLinecap="round" />
    </svg>
  );
}
