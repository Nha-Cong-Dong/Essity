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

// V22: one motif (the `hl-word` highlighter under an h1 phrase, globals.css) and one mascot. The V21
// decorations below draw nothing; groups 1-3 remove their call sites, then they are deleted.
/** @deprecated V22 draws no stickers. */
export function NoteSticker(_props: { children?: ReactNode; className?: string }) {
  return null;
}

/** @deprecated V22 draws no notebook margin. */
export function MarginRule(_props: { className?: string }) {
  return null;
}

/** @deprecated V22 draws no watermark. */
export function Watermark(_props: { className?: string }) {
  return null;
}
