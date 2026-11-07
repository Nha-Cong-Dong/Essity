"use client";

import { useEffect, useRef } from "react";

import { Doodle, type DoodleName } from "@/components/icons/doodle";
import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/today", label: "Hôm nay", doodle: "lich" },
  { href: "/subjects", label: "Môn học", doodle: "sach-mo" },
  { href: "/kho-kien-thuc", label: "Kho kiến thức", doodle: "the" },
  { href: "/graph", label: "Đồ thị", doodle: "do-thi" },
  { href: "/stats", label: "Thống kê", doodle: "dau-tich" },
] as const satisfies readonly { href: string; label: string; doodle: DoodleName }[];

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
        "min-[1024px]:static min-[1024px]:mt-8 min-[1024px]:rail-collapsed:items-center min-[1024px]:h-auto min-[1024px]:flex-col min-[1024px]:justify-start min-[1024px]:gap-1 min-[1024px]:overflow-visible min-[1024px]:border-t-0 min-[1024px]:bg-transparent min-[1024px]:pb-0",
      )}
    >
      {NAV.map(({ href, label, doodle }) => (
        <a
          key={href}
          href={href}
          aria-current={href === current ? "page" : undefined}
          className={cn(
            "group relative flex min-h-11 min-w-16 flex-1 flex-col items-center justify-center gap-0.5 px-1 first:pl-3 last:pr-3 text-chip font-medium whitespace-nowrap text-ink-soft no-underline hover:text-ink",
            "min-[1024px]:rail-collapsed:size-11 min-[1024px]:rail-collapsed:min-w-0 min-[1024px]:rail-collapsed:justify-center min-[1024px]:rail-collapsed:self-center min-[1024px]:rail-collapsed:gap-0 min-[1024px]:rail-collapsed:rounded-full min-[1024px]:rail-collapsed:px-0 min-[1024px]:first:pl-3 min-[1024px]:last:pr-3 min-[1024px]:rail-collapsed:first:pl-0 min-[1024px]:rail-collapsed:last:pr-0 min-[1024px]:h-10 min-[1024px]:flex-none min-[1024px]:flex-row min-[1024px]:justify-start min-[1024px]:gap-3 min-[1024px]:rounded-control min-[1024px]:px-3 min-[1024px]:text-body min-[1024px]:hover:bg-sheet/60",
            // The current item: pink on the bar (with a dot), a white sheet pill with a pink icon, a hairline, elev-1 and a pink bar on the rail.
            "aria-[current=page]:font-semibold aria-[current=page]:text-hong-text min-[1024px]:aria-[current=page]:bg-sheet min-[1024px]:aria-[current=page]:font-bold min-[1024px]:aria-[current=page]:shadow-sheet min-[1024px]:aria-[current=page]:[&_svg]:text-hong-text",
            // ... with a 3px pink bar at its left edge (DESIGN-V4 D); on the tab bar the dot below says it instead.
            "min-[1024px]:aria-[current=page]:before:absolute min-[1024px]:aria-[current=page]:before:inset-y-2.5 min-[1024px]:aria-[current=page]:before:left-0 min-[1024px]:aria-[current=page]:before:w-[3px] min-[1024px]:aria-[current=page]:before:rounded-full min-[1024px]:aria-[current=page]:before:bg-hong min-[1024px]:aria-[current=page]:before:content-['']",
            "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
          )}
        >
          <Doodle name={doodle} size={24} className="size-[22px] shrink-0 min-[1024px]:size-5" />
          {label.startsWith("Kho") ? (
            <span className="min-[1024px]:rail-collapsed:sr-only">
              Kho<span className="hidden min-[1024px]:inline">{" " + label.slice(4)}</span>
            </span>
          ) : (
            <span className="min-[1024px]:rail-collapsed:sr-only">{label}</span>
          )}
          {/* Collapsed rail: the name as a tooltip on hover and keyboard focus. */}
          <span
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-full z-(--z-menu) ml-2 hidden -translate-y-1/2 rounded-control bg-ink px-2.5 py-1 text-meta whitespace-nowrap text-bg shadow-over group-focus-visible:rail-collapsed:min-[1024px]:block group-hover:rail-collapsed:min-[1024px]:block"
          >
            {label}
          </span>
          <span
            aria-hidden="true"
            className="absolute bottom-0.5 hidden size-1 rounded-full bg-hong group-aria-[current=page]:block min-[1024px]:group-aria-[current=page]:hidden"
          />
        </a>
      ))}
    </nav>
  );
}
