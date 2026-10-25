import type { ReactNode } from "react";

import { MainNav, type NavItem } from "@/components/main-nav";
import { cn } from "@/lib/utils";

// The three frames of design system v3.1 §5. Header and content share one container, so the
// logo and the page start at the same left edge.

const CONTAINER = "mx-auto w-full max-w-(--page-max) px-(--page-gutter)";

export type { NavItem } from "@/components/main-nav";

function Logo() {
  return <span className="font-display text-logo text-hong">Essity</span>;
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
        <div className={cn(CONTAINER, "flex h-(--header-h) items-center gap-2 max-[360px]:gap-1 min-[401px]:gap-4 min-[901px]:gap-10")}>
          <Logo />
          <MainNav current={current} />
          <div className="ml-auto flex min-w-10 justify-end">{account}</div>
        </div>
      </header>
      <main className={cn(CONTAINER, "flex flex-1 flex-col pt-10 pb-24")}>{children}</main>
    </div>
  );
}

/**
 * Focus frame for a review session (/review/*): no navigation, only progress and the way out
 * ("Dừng tại đây"). The 3px bar is not split per question, so it hints at nothing ahead.
 */
export function FocusShell({
  position,
  total,
  exit,
  children,
}: {
  position: number;
  total: number;
  exit: ReactNode;
  children: ReactNode;
}) {
  const percent = total > 0 ? Math.round((position / total) * 100) : 0;
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-line">
        <div className={cn(CONTAINER, "flex h-(--header-focus-h) items-center gap-4")}>
          <span className="text-meta whitespace-nowrap text-ink-soft tabular-nums">
            Câu {position} / {total}
          </span>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={position}
            aria-label={`Câu ${position} trên ${total}`}
            className="h-[3px] w-40 overflow-hidden rounded-full bg-line"
          >
            <div className="h-[3px] rounded-full bg-hong" style={{ width: `${percent}%` }} />
          </div>
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
