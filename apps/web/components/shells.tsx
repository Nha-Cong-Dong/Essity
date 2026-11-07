import { CommandSlot } from "@/components/command-slot";
import type { ReactNode } from "react";

import { ArtBackdrop } from "@/components/art-backdrop";
import { BrandMark } from "@/components/brand-mark";
import { MainNav, type NavItem } from "@/components/main-nav";
import { RailToggle } from "@/components/rail-toggle";
import { cn } from "@/lib/utils";

// The three frames of design system v3.1 §5. Header and content share one container, so the
// logo and the page start at the same left edge.

const CONTAINER = "mx-auto w-full max-w-(--page-max) px-(--page-gutter)";

export type { NavItem } from "@/components/main-nav";

function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-display text-logo tracking-[-0.02em] text-(color:--logo-ink)", className)}>
      <BrandMark size={28} />
      <span>Essity</span>
    </span>
  );
}

const COLUMN = {
  read: "max-w-160",
  session: "max-w-(--col-session)",
  full: "max-w-280",
  // UI-A: the reading width of list screens (Đề cương, Luyện tập, Kho, Thống kê): ~960, centred in the page.
  wide: "max-w-240 mx-auto",
} as const;

/**
 * One column for a page inside AppShell (UI-1a). `read`, `session` and `full` start at the left edge
 * of the container (`mr-auto`); `wide` (UI-A) is the ~960 column list screens centre in the page.
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
 * Regular frame (V22, "giấy trắng, một bút hồng"): a neutral page. From 1024px a 232px rail on the
 * same ground holds the logo, the nav and the account row; it is sticky and as tall as the window
 * (100dvh), so it covers a long page. Below, a 48/56px top bar keeps the logo and the account
 * button and the nav becomes a tab bar at the foot (see MainNav). The page is one container
 * beside the rail.
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
    <div className="relative isolate flex min-h-full flex-1 flex-col bg-bg min-[1024px]:flex-row">
      <ArtBackdrop />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-(--z-header) focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-full focus:bg-sheet focus:px-4 focus:font-medium focus:text-ink focus:inset-ring-2 focus:inset-ring-focus"
      >
        Bỏ qua tới nội dung
      </a>
      <header
        id="app-rail"
        className={cn(
          "sticky top-0 z-(--z-header) flex h-12 items-center gap-4 border-b border-line bg-bg px-4 sm:h-14",
          "lg:h-dvh lg:w-(--rail-w) lg:shrink-0 lg:flex-col lg:items-stretch lg:gap-0 lg:self-start lg:border-r lg:border-b-0 lg:border-line lg:bg-rail lg:px-4 lg:pt-8 lg:pb-6",
          "lg:transition-[width] lg:duration-150 motion-reduce:transition-none lg:rail-collapsed:px-2",
        )}
      >
        {/* UI-NITS-0811: "Essity" and the collapse button share the top row; the button sits flush on the rail's outer right edge (rail padding cancelled). Collapsed: mark above button. */}
        <div className="flex items-center gap-2 min-[1024px]:-mr-4 min-[1024px]:justify-between min-[1024px]:pl-3 min-[1024px]:rail-collapsed:mr-0 min-[1024px]:rail-collapsed:flex-col min-[1024px]:rail-collapsed:justify-center min-[1024px]:rail-collapsed:gap-2 min-[1024px]:rail-collapsed:pl-0">
          <Logo className="min-[1024px]:rail-collapsed:[&>span]:sr-only min-[1024px]:rail-collapsed:gap-0" />
          <RailToggle />
        </div>
        <MainNav current={current} />
        <div className="ml-auto flex min-w-10 items-center justify-end min-[1024px]:mt-auto min-[1024px]:ml-0 min-[1024px]:flex-col min-[1024px]:items-stretch min-[1024px]:justify-start min-[1024px]:gap-2">
          <div className="min-[1024px]:rail-collapsed:self-center">{account}</div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className={cn(CONTAINER, "outline-none flex min-w-0 flex-1 flex-col pt-6 pb-[calc(56px+env(safe-area-inset-bottom)+16px)] min-[1024px]:pt-10 min-[1024px]:pb-24")}>
        {/* T9.3: the subject's command bar is drawn here (components/command-live.tsx). */}
        <CommandSlot className="empty:hidden" />
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
    <div className="flex min-h-full flex-1 flex-col [--sunken:var(--sheet)]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-(--z-header) focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-full focus:bg-sheet focus:px-4 focus:font-medium focus:text-ink focus:inset-ring-2 focus:inset-ring-focus"
      >
        Bỏ qua tới nội dung
      </a>
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
      <main id="main" tabIndex={-1} className={cn(CONTAINER, "outline-none flex flex-1 flex-col pt-14 pb-24")}>
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
      <main className={cn(CONTAINER, "relative flex flex-1 items-start justify-center overflow-x-clip pt-12 pb-24 min-[900px]:items-center min-[900px]:pt-0 min-[900px]:pb-16")}>
        {children}
      </main>
    </div>
  );
}
