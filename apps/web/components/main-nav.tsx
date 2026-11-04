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
 * The notebook spine of AppShell (V21): a 96px rail on the left from 901px up, a 64px tab bar at
 * the foot of the screen below. The current item is "stuck" to the page (ground colour, rounded
 * on the page side) on the rail, and gets a rose tab on the bar. Touch targets stay ≥ 44px and
 * labels ≥ 12px. Where the bar still has to scroll (enlarged text), the current item is brought
 * into view along the nav only: `nearest` on both axes never scrolls the page.
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
        "z-(--z-header) flex min-w-0 bg-rail text-on-rail",
        // Phone: tab bar at the foot.
        "fixed inset-x-0 bottom-0 h-16 flex-row justify-around overflow-x-auto px-2",
        // Desktop: a column under the logo, inside the rail.
        "min-[901px]:inset-x-auto min-[901px]:top-24 min-[901px]:bottom-auto min-[901px]:left-0 min-[901px]:h-auto min-[901px]:w-24 min-[901px]:flex-col min-[901px]:justify-start min-[901px]:gap-1.5 min-[901px]:overflow-visible min-[901px]:bg-transparent min-[901px]:px-0",
      )}
    >
      {NAV.map(({ href, label, icon: Icon }) => (
        <a
          key={href}
          href={href}
          aria-current={href === current ? "page" : undefined}
          className={cn(
            "flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-1 px-1 text-meta leading-tight font-medium text-on-rail no-underline",
            "min-[901px]:ml-5 min-[901px]:flex-none min-[901px]:[border-radius:14px_0_0_14px] min-[901px]:py-2.5 min-[901px]:text-center",
            // The current item: a rose tab on the bar, merged into the page on the rail.
            "aria-[current=page]:bg-rose-100 aria-[current=page]:font-semibold aria-[current=page]:text-ink min-[901px]:aria-[current=page]:bg-ground",
            // Phone only: the tab carries its own rounded corners.
            "max-[900px]:aria-[current=page]:rounded-control",
            // The nav may scroll and clips what is outside it: the ring goes inside; on the pink
            // rail it is the page colour (≥ 3:1 on the rail).
            "[--focus:var(--on-rail)] aria-[current=page]:[--focus:var(--ink)] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus",
          )}
        >
          <Icon aria-hidden="true" focusable="false" strokeWidth={1.8} className="size-[22px] shrink-0" />
          {label.startsWith("Kho") ? (
            <span>
              Kho<span className="max-[900px]:hidden">{" " + label.slice(4)}</span>
            </span>
          ) : (
            <span>{label}</span>
          )}
        </a>
      ))}
    </nav>
  );
}
