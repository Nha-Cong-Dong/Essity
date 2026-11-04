import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// The list pattern of the landing ("Học gì tiếp", "Luyện đúng dạng đề"), as components (V22). Source:
// components/landing/landing.module.css .nxCard .nxToc .nxN .nxS .nxNext .nxKinds .nxPick .nxWhy
// .nxChip. A tile in --hong-tint (r24, no border, no shadow) holds rows on the page colour; the one
// "suggested / next" row of a tile is drawn in --cam, the app's only second colour, with an arrow and
// words ("Tiếp theo"), never colour alone.

/** The tile: a name on the left, an italic hint on the right ("Gợi ý, bạn chọn"), then rows. */
export function NxList({
  title,
  hint,
  children,
  className,
  as: Tag = "ul",
  titleAs: Title = "h2",
}: {
  title?: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
  className?: string;
  as?: "ul" | "ol" | "div";
  titleAs?: "h2" | "h3" | "b";
}) {
  return (
    <section data-nx className={cn("min-w-0 rounded-tile bg-hong-tint p-6 max-[700px]:p-4", className)}>
      {title || hint ? (
        <div className="flex items-baseline justify-between gap-3 pb-3.5">
          <Title className="m-0 font-display text-tile">
            {title}
          </Title>
          {hint ? <span className="text-meta italic text-ink-soft">{hint}</span> : null}
        </div>
      ) : null}
      <Tag className="m-0 flex list-none flex-col gap-1.5 p-0">{children}</Tag>
    </section>
  );
}

const ROW = "grid min-h-12 grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 rounded-row bg-bg px-3.5 py-1.5 text-body min-[641px]:min-h-11.5";
const NEXT = "bg-[color-mix(in_srgb,var(--cam)_15%,var(--bg))] font-semibold inset-ring-[1.5px] inset-ring-cam";
const PICK = "bg-[color-mix(in_srgb,var(--cam)_12%,var(--bg))] inset-ring-[1.5px] inset-ring-cam";

/**
 * A row: a lead cell (number, letter tile, tick), the name (wraps to two lines), the state at the
 * right. `next` is the one cam row: the state is cam with an arrow, and `why` is the line under the
 * name. With `href` the row is a link and hovers to --sunken.
 */
export function NxRow({
  lead,
  children,
  state,
  why,
  next = false,
  href,
  className,
}: {
  lead?: ReactNode;
  children?: ReactNode;
  state?: ReactNode;
  why?: ReactNode;
  next?: boolean;
  href?: string;
  className?: string;
}) {
  const body = (
    <>
      <span className="tabular-nums text-ink-soft">{lead}</span>
      <span className="min-w-0 break-words [overflow-wrap:normal]">
        {children}
        {why ? <span className="mt-1 block text-meta font-semibold text-cam">{why}</span> : null}
      </span>
      <span className={cn("text-meta whitespace-nowrap text-ink-soft", next && "font-semibold text-cam")}>
        {next ? <span aria-hidden="true">→ </span> : null}
        {state}
      </span>
    </>
  );
  const cls = cn(ROW, next && NEXT, href && "text-ink no-underline hover:bg-sunken", className);
  return href ? (
    <li>
      <a href={href} className={cls}>
        {body}
      </a>
    </li>
  ) : (
    <li className={cls}>{body}</li>
  );
}

/** A question-kind chip: a pill, hong 10%, with an inset 1px edge. */
export function NxChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-full bg-hong/10 px-3 text-meta font-semibold text-ink inset-ring-1 inset-ring-hong/35",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A row of "kinds": the chip above, the sample question below; `pick` is the cam row with its reason. */
export function NxKind({
  chip,
  children,
  why,
  pick = false,
  className,
}: {
  chip: ReactNode;
  children?: ReactNode;
  why?: ReactNode;
  pick?: boolean;
  className?: string;
}) {
  return (
    <li className={cn("flex flex-col items-start gap-2 rounded-row bg-bg px-4 py-3.5", pick && PICK, className)}>
      <NxChip>{chip}</NxChip>
      <span className="text-body leading-snug">
        {children}
        {why ? <span className="mt-1 block text-meta font-semibold text-cam">{why}</span> : null}
      </span>
    </li>
  );
}

/** The cam classes for rows that are not an NxRow (a tree row, a practice question): one source of --cam. */
export const NX_CAM = {
  row: NEXT,
  pick: "bg-cam/12 inset-ring-[1.5px] inset-ring-cam",
  text: "font-semibold text-cam",
} as const;
