import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// The three frames of DESIGN.md §5 (canvas Shells artboard).

const NAV = [
  { href: "/today", label: "Hôm nay" },
  { href: "/subjects", label: "Môn học" },
  // "Tiến độ" stays hidden until US-10 is built (M5).
] as const;

export type NavItem = (typeof NAV)[number]["href"];

function Logo() {
  return (
    <span className="font-display text-[24px] font-bold tracking-[-0.03em] text-hong">
      Essity
    </span>
  );
}

/**
 * Regular frame: logo, three pill links (the current one on a faint `--line`), the account
 * button (T1.12), and a left-aligned column of at most 1120px with 80px margins.
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
      <header className="flex h-20 items-center justify-between border-b border-line px-6 md:px-20">
        <Logo />
        <nav aria-label="Chính" className="flex gap-2">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              aria-current={item.href === current ? "page" : undefined}
              className={cn(
                "flex h-11 items-center rounded-full px-[18px] text-[15px] font-medium text-ink-soft no-underline",
                "aria-[current=page]:bg-[color-mix(in_srgb,var(--line)_55%,transparent)] aria-[current=page]:font-semibold aria-[current=page]:text-ink",
              )}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="flex min-w-11 justify-end">{account}</div>
      </header>
      <main className="mx-auto flex w-full max-w-[1120px] flex-1 flex-col px-6 py-12 md:px-0">
        {children}
      </main>
    </div>
  );
}

/**
 * Focus frame for a review session (/review/*): no navigation, only progress and the way out
 * ("Dừng tại đây"). The 4px bar is not split per question, so it hints at nothing ahead.
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
      <header className="flex h-18 items-center justify-between border-b border-line px-6 md:px-20">
        <div className="flex items-center gap-5">
          <span className="font-semibold">
            Câu {position}/{total}
          </span>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={position}
            aria-label={`Câu ${position} trên ${total}`}
            className="h-1 w-60 overflow-hidden rounded-full bg-line"
          >
            <div className="h-1 rounded-full bg-hong" style={{ width: `${percent}%` }} />
          </div>
        </div>
        {exit}
      </header>
      <main className="mx-auto flex w-full max-w-[900px] flex-1 flex-col px-6 py-12">
        {children}
      </main>
    </div>
  );
}

/** Account frame (/login, /register...): only the logo, content centred on the page. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="flex h-20 items-center px-6 md:px-20">
        <Logo />
      </header>
      <main className="flex flex-1 items-start justify-center px-6 py-12">{children}</main>
    </div>
  );
}
