import { cn } from "@/lib/utils";

// DESIGN-V4 (design-system.md A5): the field's one pattern layer (a fading grid of fine cells) and the
// 14-point sticker, white on the field. Decoration only: aria-hidden, no words.
const GRID =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28'%3E%3Cpath d='M28 0H0V28' fill='none' stroke='white' stroke-opacity='.12'/%3E%3C/svg%3E\")";
const FADE = "linear-gradient(to left, #000 0, transparent 70%)";

export function FieldGrain({ className }: { className?: string }) {
  return (
    <i
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 -z-10", className)}
      style={{ backgroundImage: GRID, WebkitMaskImage: FADE, maskImage: FADE }}
    />
  );
}

const STAR = "M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z";

export function StarSticker({ className, children }: { className?: string; children?: React.ReactNode }) {
  return (
    <span aria-hidden="true" className={cn("pointer-events-none absolute grid place-items-center", className)}>
      <svg viewBox="0 0 100 100" className="absolute inset-0 size-full -rotate-8 drop-shadow-[0_8px_10px_rgb(0_0_0/0.25)]">
        <path d={STAR} className="fill-on-plum stroke-on-plum" strokeWidth="2" strokeLinejoin="round" />
      </svg>
      {children}
    </span>
  );
}
