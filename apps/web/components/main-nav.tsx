"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export const NAV = [
  { href: "/today", label: "Hôm nay" },
  { href: "/subjects", label: "Môn học" },
  // "Tiến độ" stays hidden until US-10 is built (M5); a third item will need the header redone.
] as const;

export type NavItem = (typeof NAV)[number]["href"];

/**
 * The pill nav of AppShell. Below 360px the pills and gaps tighten so both labels fit beside the
 * logo and the account button (T2.3c, risk register R46). Where the nav still has to scroll (a
 * narrower screen, a fallback font, enlarged text), the current item is brought into view along
 * the nav only: `nearest` on both axes never scrolls the page.
 */
export function MainNav({ current }: { current?: NavItem }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView?.({ inline: "nearest", block: "nearest" });
  }, [current]);
  return (
    <nav ref={ref} aria-label="Chính" className="flex min-w-0 gap-1 overflow-x-auto max-[360px]:gap-0.5">
      {NAV.map((item) => (
        <a
          key={item.href}
          href={item.href}
          aria-current={item.href === current ? "page" : undefined}
          className={cn(
            "flex h-10 shrink-0 items-center rounded-full px-2.5 text-body font-medium whitespace-nowrap text-ink-soft no-underline hover:text-ink max-[360px]:px-1.5 min-[401px]:px-3 min-[901px]:px-4",
            "aria-[current=page]:bg-ink aria-[current=page]:font-semibold aria-[current=page]:text-bg",
          )}
        >
          {item.label}
        </a>
      ))}
    </nav>
  );
}
