import type { ReactNode } from "react";

import { MainNav, type NavItem } from "@/components/main-nav";
import { cn } from "@/lib/utils";

// The three frames of design system v3.1 §5. Header and content share one container, so the
// logo and the page start at the same left edge.

const CONTAINER = "mx-auto w-full max-w-(--page-max) px-(--page-gutter)";

export type { NavItem } from "@/components/main-nav";

function Logo() {
  return (
    <span className="font-display text-logo text-hong max-[480px]:flex max-[480px]:h-(--header-h) max-[480px]:items-center">
      Essity
    </span>
  );
}

/**
 * Regular frame: a 64px header with the logo, the pill nav right after it (the current item in
 * inverted ink) and the account button at the right edge; then the page.
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
    <div className="flex min-h-full flex-1 flex-col">
      <header className="sticky top-0 z-(--z-header) border-b border-line bg-bg">
        <div
          className={cn(
            CONTAINER,
            // Under 480px three nav items cannot share a row with the logo and the account button
            // at 320 (T9.5): the nav drops to its own row, below, as wide as the page.
            "flex h-(--header-h) items-center gap-4 max-[480px]:h-auto max-[480px]:flex-wrap max-[480px]:gap-x-2 max-[480px]:gap-y-0 min-[901px]:gap-10",
          )}
        >
          <Logo />
          <MainNav current={current} />
          <div className="ml-auto flex min-w-10 justify-end max-[480px]:order-1 max-[480px]:h-(--header-h) max-[480px]:items-center">
            {account}
          </div>
        </div>
      </header>
      <main className={cn(CONTAINER, "flex flex-1 flex-col pt-10 pb-24")}>{children}</main>
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
