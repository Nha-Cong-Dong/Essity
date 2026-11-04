import type { ReactNode } from "react";

import { MainNav, type NavItem } from "@/components/main-nav";
import { cn } from "@/lib/utils";

// The three frames of design system v3.1 §5. Header and content share one container, so the
// logo and the page start at the same left edge.

const CONTAINER = "mx-auto w-full max-w-(--page-max) px-(--page-gutter)";

export type { NavItem } from "@/components/main-nav";

function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("font-display text-logo text-hong", className)}>
      Essity
    </span>
  );
}

const COLUMN = {
  read: "max-w-160",
  session: "max-w-(--col-session)",
  full: "max-w-280",
} as const;

/**
 * One column for a page inside AppShell (UI-1a). Every width starts at the left edge of the
 * container, under the logo: `mr-auto`, never `mx-auto`, so no screen has its own left edge.
 */
export function PageColumn({
  width = "full",
  className,
  children,
  ...rest
}: { width?: keyof typeof COLUMN } & React.ComponentProps<"div">) {
  return (
    <div {...rest} className={cn("mr-auto w-full", COLUMN[width], className)}>
      {children}
    </div>
  );
}

/**
 * Regular frame (V21, "cuốn vở"): a pink ground with a dot grid. From 901px a 96px spine on the
 * left holds the logo, the nav and the account button; below it a thin top bar keeps the logo and
 * the account button, and the nav becomes a tab bar at the foot (see MainNav). The page content
 * is one container beside the spine.
 */
export function AppShell({
  current,
  account,
  children,
}: {
  current?: NavItem;
  account?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="ground-dots flex min-h-full flex-1 flex-col bg-ground min-[901px]:pl-24">
      <header
        className={cn(
          "sticky top-0 z-(--z-header) border-b border-line bg-ground",
          "min-[901px]:fixed min-[901px]:inset-y-0 min-[901px]:left-0 min-[901px]:w-24 min-[901px]:border-b-0 min-[901px]:bg-rail",
        )}
      >
        <div
          className={cn(
            "flex h-(--header-h) items-center gap-4 px-(--page-gutter)",
            "min-[901px]:h-full min-[901px]:flex-col min-[901px]:items-center min-[901px]:justify-start min-[901px]:gap-0 min-[901px]:px-0 min-[901px]:pt-7",
          )}
        >
          <Logo className="min-[901px]:text-on-rail" />
          <div className="ml-auto flex min-w-10 justify-end min-[901px]:fixed min-[901px]:bottom-28 min-[901px]:left-0 min-[901px]:ml-0 min-[901px]:w-24 min-[901px]:justify-center">
            {account}
          </div>
          <span aria-hidden="true" data-motif="holes" className="hidden min-[901px]:fixed min-[901px]:bottom-5 min-[901px]:left-0 min-[901px]:flex min-[901px]:w-24 min-[901px]:flex-col min-[901px]:items-center min-[901px]:gap-5">
            {[0, 1, 2].map((k) => (
              <i key={k} className="size-3 rounded-full bg-ground shadow-[inset_0_2px_3px_rgb(0_0_0/0.35)]" />
            ))}
          </span>
        </div>
      </header>
      <MainNav current={current} />
      <main className={cn(CONTAINER, "flex flex-1 flex-col pt-10 pb-24 max-[900px]:pt-6 max-[900px]:pb-28")}>
        {/* T9.3: the subject's command bar is drawn here (components/command-live.tsx). */}
        <div data-command-slot className="empty:hidden" />
        {children}
      </main>
    </div>
  );
}

/**
 * Focus frame for a review session (/review/*): no navigation, only progress and the way out
 * ("Dừng tại đây"). The 3px bar is not split per question, so it hints at nothing ahead. Without a
 * total (loading, or the session over) neither shows.
 */
export function FocusShell({
  position,
  total,
  exit,
  title,
  children,
}: {
  position: number;
  total: number;
  exit: ReactNode;
  /** Left of the exit when there is no progress to show: the study session names its subject. */
  title?: ReactNode;
  children: ReactNode;
}) {
  const percent = total > 0 ? Math.round((position / total) * 100) : 0;
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-line">
        <div className={cn(CONTAINER, "flex h-(--header-focus-h) items-center gap-4")}>
          {total > 0 && (
            <>
              <span className="text-meta whitespace-nowrap text-ink-soft tabular-nums">
                Câu {position} / {total}
              </span>
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={total}
                aria-valuenow={position}
                aria-label={`Câu ${position} trên ${total}`}
                className="h-[3px] w-40 overflow-hidden rounded-full bg-line max-[900px]:w-24"
              >
                <div className="h-[3px] rounded-full bg-hong" style={{ width: `${percent}%` }} />
              </div>
            </>
          )}
          {title ? <div className="min-w-0 truncate text-meta text-ink-soft">{title}</div> : null}
          <div className="ml-auto text-meta whitespace-nowrap text-ink-soft">{exit}</div>
        </div>
      </header>
      <main className={cn(CONTAINER, "flex flex-1 flex-col pt-14 pb-24")}>
        <div className="mx-auto w-full max-w-(--col-focus)">{children}</div>
      </main>
    </div>
  );
}

/** Account frame (/login, /register...): only the logo, one sheet centred on the page. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header>
        <div className={cn(CONTAINER, "flex h-(--header-h) items-center")}>
          <Logo />
        </div>
      </header>
      <main className={cn(CONTAINER, "relative flex flex-1 items-start justify-center overflow-x-clip pt-12 pb-24")}>
        {children}
      </main>
    </div>
  );
}
