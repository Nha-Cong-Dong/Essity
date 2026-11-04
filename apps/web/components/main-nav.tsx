"use client";

import { BookOpen, Library, LineChart, Network, Sun, type LucideIcon } from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/today", label: "Hôm nay", icon: Sun },
  { href: "/subjects", label: "Môn học", icon: BookOpen },
  { href: "/kho-kien-thuc", label: "Kho kiến thức", icon: Library },
  { href: "/graph", label: "Đồ thị", icon: Network },
  { href: "/stats", label: "Thống kê", icon: LineChart },
] as const satisfies readonly { href: string; label: string; icon: LucideIcon }[];

export type NavItem = (typeof NAV)[number]["href"];

/**
 * The navigation of AppShell (V22): a column in the left rail from 1024px up (the current item on a
 * sunken pill, its icon pink), a 56px tab bar at the foot of the screen below (the current item
 * pink with a 4px dot; 13px labels on one line, "Kho" for the long one). Every item is ≥ 44px.
 * Where the bar still has to scroll (enlarged text), the current item is brought into view along the
 * nav only: `nearest` on both axes never scrolls the page.
 */
export function MainNav({ current }: { current?: NavItem }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView?.({ inline: "nearest", block: "nearest" });
  }, [current]);
  return (
    <nav
      ref={ref}
      aria-label="Chính"
      className={cn(
        "z-(--z-header) flex min-w-0 bg-sheet",
        // Phone and tablet: tab bar at the foot, above the home indicator.
        "fixed inset-x-0 bottom-0 h-[calc(56px+env(safe-area-inset-bottom))] flex-row justify-around overflow-x-auto border-t border-line pb-[env(safe-area-inset-bottom)]",
        // Desktop: a column under the logo, inside the rail.
        "min-[1024px]:static min-[1024px]:mt-8 min-[1024px]:h-auto min-[1024px]:flex-col min-[1024px]:justify-start min-[1024px]:gap-1 min-[1024px]:overflow-visible min-[1024px]:border-t-0 min-[1024px]:bg-transparent min-[1024px]:pb-0",
      )}
    >
      {NAV.map(({ href, label, icon: Icon }) => (
        <a
          key={href}
          href={href}
          aria-current={href === current ? "page" : undefined}
          className={cn(
            "group relative flex min-h-11 min-w-16 flex-1 flex-col items-center justify-center gap-0.5 px-1 text-chip font-medium whitespace-nowrap text-ink-soft no-underline hover:text-ink",
            "min-[1024px]:h-10 min-[1024px]:flex-none min-[1024px]:flex-row min-[1024px]:justify-start min-[1024px]:gap-3 min-[1024px]:rounded-control min-[1024px]:px-3 min-[1024px]:text-body min-[1024px]:hover:bg-sunken",
            // The current item: pink on the bar (with a dot), a sunken pill with a pink icon on the rail.
            "aria-[current=page]:font-semibold aria-[current=page]:text-hong min-[1024px]:aria-[current=page]:bg-sunken min-[1024px]:aria-[current=page]:text-ink min-[1024px]:aria-[current=page]:[&_svg]:text-hong",
            "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
          )}
        >
          <Icon aria-hidden="true" focusable="false" strokeWidth={1.8} className="size-[22px] shrink-0 min-[1024px]:size-5" />
          {label.startsWith("Kho") ? (
            <span>
              Kho<span className="hidden min-[1024px]:inline">{" " + label.slice(4)}</span>
            </span>
          ) : (
            <span>{label}</span>
          )}
          <span
            aria-hidden="true"
            className="absolute bottom-0.5 hidden size-1 rounded-full bg-hong group-aria-[current=page]:block min-[1024px]:group-aria-[current=page]:hidden"
          />
        </a>
      ))}
    </nav>
  );
}
