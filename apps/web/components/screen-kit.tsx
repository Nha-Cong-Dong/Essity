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

/** A section's heading (V22: plain; the highlighter belongs to the h1 of a screen only). */
export function SectionHead({ title, aside }: { title: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <h2 className="m-0 font-display text-lead">{title}</h2>
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

/**
 * The head of a screen (V22): an optional breadcrumb, the h1 with the one highlighter
 * band under `highlight` (a phrase of the title, once per screen, none on deep screens), a one-line
 * conclusion under it and a primary action on the right. The h1 breaks between words only.
 */
export function ScreenHeader({
  title,
  highlight,
  crumb,
  lede,
  action,
  className,
}: {
  title: string;
  /** A phrase inside `title`; omit it on deep screens (syllabus, practice, graph, forms). */
  highlight?: string;
  crumb?: ReactNode;
  lede?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const at = highlight ? title.indexOf(highlight) : -1;
  return (
    <header className={cn("mb-6 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 min-[1024px]:mb-8", className)}>
      <div className="flex min-w-0 flex-1 basis-80 flex-col gap-2">
        {crumb ? <p className="m-0 text-meta text-ink-soft">{crumb}</p> : null}
        <h1 className="m-0 text-title tracking-tight text-balance [overflow-wrap:normal] [word-break:normal] hyphens-manual">
          {at < 0 ? (
            title
          ) : (
            <>
              {title.slice(0, at)}
              <span data-motif="hl-word" className="hl-word">
                {highlight}
              </span>
              {title.slice(at + (highlight?.length ?? 0))}
            </>
          )}
        </h1>
        {lede ? <p className="m-0 max-w-prose text-body text-ink-soft">{lede}</p> : null}
      </div>
      {action ? <div className="max-sm:w-full">{action}</div> : null}
    </header>
  );
}

/**
 * A figure (V22): the label above in meta, the number in the display face, an optional unit beside it.
 * Without data show "—" and a short line, never "chưa có" at figure size. No background: several
 * Stats sit in one card divided by 1px lines.
 */
export function Stat({
  label,
  value,
  unit,
  hint,
  size = "stat",
  className,
}: {
  label: ReactNode;
  /** `null` draws "—" at body size. */
  value: ReactNode | null;
  unit?: ReactNode;
  hint?: ReactNode;
  /** `display` is the one big number of a screen (64, mobile 44). */
  size?: "stat" | "display";
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-meta text-ink-soft">{label}</span>
      {value === null ? (
        <span className="text-body text-ink-soft">—</span>
      ) : (
        <span className="flex items-baseline gap-2">
          <span className={size === "display" ? "text-display" : "text-verdict"}>{value}</span>
          {unit ? <span className="text-meta text-ink-soft">{unit}</span> : null}
        </span>
      )}
      {hint ? <span className="text-meta text-ink-soft">{hint}</span> : null}
    </div>
  );
}

/**
 * A list row (V22): a fixed 36px lead cell, a title and a meta line, a trailing slot; 56px high
 * (64 with a meta line), divided from the next by a 1px line inside its card, no zebra. With `href`
 * the whole row is the link and hovers to --sunken.
 */
export function Row({
  lead,
  title,
  meta,
  trailing,
  href,
  className,
}: {
  lead?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  trailing?: ReactNode;
  href?: string;
  className?: string;
}) {
  const body = (
    <>
      <span className="flex size-9 shrink-0 items-center justify-center">{lead}</span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-body font-semibold break-words">{title}</span>
        {meta ? <span className="text-meta text-ink-soft break-words">{meta}</span> : null}
      </span>
      {trailing ? <span className="shrink-0 text-meta text-ink-soft">{trailing}</span> : null}
    </>
  );
  const cls = cn("flex items-center gap-3 border-b border-line py-2 last:border-b-0", meta ? "min-h-16" : "min-h-14", className);
  return href ? (
    <a href={href} className={cn(cls, "text-ink no-underline hover:bg-sunken")}>
      {body}
    </a>
  ) : (
    <div className={cls}>{body}</div>
  );
}
