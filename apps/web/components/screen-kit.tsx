import type { ReactNode } from "react";

import { Mascot, type MascotPose } from "@/components/mascot";
import { cn } from "@/lib/utils";

// Phase B (04/11): the small kit that gives the inner screens the landing's rhythm. One solid pink
// surface per screen at most (ScreenHero tone="hong"), big titles, roomy vertical rhythm, tiles
// with a thin pink top edge. Tokens only; every part wraps at 320 px.

type Tone = "hong" | "rose" | "plain";

/** The big number of a block: shown large, once. `size="mega"` is for one number per screen. */
export function StatBig({
  value,
  label,
  hint,
  size = "display",
  className,
}: {
  value: ReactNode;
  label: ReactNode;
  hint?: ReactNode;
  size?: "display" | "mega";
  className?: string;
}) {
  return (
    <p className={cn("m-0 flex flex-col gap-1", className)}>
      <span className={cn("font-display tabular-nums", size === "mega" ? "text-mega" : "text-display")}>{value}</span>
      <span className="text-read">{label}</span>
      {hint ? <span className="text-meta opacity-80">{hint}</span> : null}
    </p>
  );
}

/** The head of a screen: title, one line under it, a stat, one action, an optional mascot. */
export function ScreenHero({
  title,
  eyebrow,
  lede,
  action,
  stat,
  mascot,
  tone = "plain",
  className,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  lede?: ReactNode;
  action?: ReactNode;
  stat?: { value: ReactNode; label: ReactNode; hint?: ReactNode };
  mascot?: MascotPose;
  tone?: Tone;
  className?: string;
}) {
  const solid = tone !== "plain";
  return (
    <section
      {...(tone === "hong" ? { "data-surface": "hong" } : tone === "rose" ? { "data-surface": "rose" } : {})}
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-10 gap-y-6",
        solid ? "rounded-tile p-6 min-[901px]:p-10" : "py-2",
        className,
      )}
    >
      <div className="flex min-w-0 flex-1 basis-80 flex-col items-start gap-3">
        {eyebrow ? <p className="m-0 text-meta font-semibold opacity-80">{eyebrow}</p> : null}
        <h1 className="m-0 font-display text-title wrap-anywhere">{title}</h1>
        {lede ? <p className="m-0 max-w-prose text-read wrap-anywhere">{lede}</p> : null}
        {action ? <div className="mt-2 max-sm:w-full">{action}</div> : null}
      </div>
      {stat ? <StatBig {...stat} /> : null}
      {mascot ? <Mascot pose={mascot} size="lg" className="max-sm:size-24" /> : null}
    </section>
  );
}

/** A card with a thin pink top edge; `rose` is the quiet secondary one. */
export function FeatureTile({
  tone = "plain",
  title,
  meta,
  children,
  className,
}: {
  tone?: "plain" | "rose";
  title?: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-tile border border-line border-t-4 border-t-hong p-6 min-[901px]:p-8",
        tone === "rose" ? "bg-rose-50" : "bg-sheet",
        className,
      )}
    >
      {title ? <h2 className="m-0 font-display text-lead wrap-anywhere">{title}</h2> : null}
      {meta ? <p className="m-0 mt-1 text-meta text-ink-soft">{meta}</p> : null}
      {children ? <div className={title ? "mt-4" : ""}>{children}</div> : null}
    </div>
  );
}

/** A section's heading with the highlighter band under the words, as the landing's. */
export function SectionHead({ title, aside }: { title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <h2 className="m-0 font-display text-lead">
        <span className="px-1" style={{ backgroundImage: "linear-gradient(to top, var(--hl-band) 35%, transparent 35%)" }}>{title}</span>
      </h2>
      {aside ? <div className="text-meta text-ink-soft">{aside}</div> : null}
    </div>
  );
}

/** Its children rise in one after another, once; the order is in CSS (globals.css [data-reveal]). */
export function RevealStack({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div data-reveal className={className}>
      {children}
    </div>
  );
}
