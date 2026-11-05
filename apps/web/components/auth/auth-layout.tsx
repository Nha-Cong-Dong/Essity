import type { ReactNode } from "react";

import { Mascot } from "@/components/mascot";

// DESIGN-V3 (§C): from 1024px the left 5/12 is the plum field (wordmark, the tagline, Bé Trang, one
// star doodle) and the form sits in a 400px sheet on the right; at 360 a 140px plum strip sits above
// the form. The page title stays the sheet's h1. Plum tokens come from W0; the fallbacks are theirs.

const PLUM = "bg-[var(--plum,#4A1638)] text-[var(--on-plum,#FFFFFF)]";

/** One account screen: the plum field with the logo, then a sheet with the page title (h1) and the form. */
export function AuthLayout({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg text-ink min-[1024px]:grid min-[1024px]:grid-cols-12">
      <aside
        data-auth="top"
        className={`relative flex h-[140px] shrink-0 flex-col justify-between overflow-hidden px-4 py-4 min-[1024px]:col-span-5 min-[1024px]:h-auto min-[1024px]:px-12 min-[1024px]:py-10 ${PLUM}`}
      >
        <a
          href="/"
          aria-label="Essity"
          className="inline-flex min-h-11 items-center self-start font-display text-logo text-[var(--on-plum,#FFFFFF)] no-underline"
        >
          Essity
        </a>
        <p className="m-0 max-w-[16ch] font-display text-lead text-balance min-[1024px]:text-title">
          Tối nay ôn gì, đã có app lo
        </p>
        <svg
          aria-hidden="true"
          focusable="false"
          viewBox="0 0 100 100"
          className="absolute right-6 top-4 size-10 fill-[var(--hl,#FFD15C)] min-[1024px]:right-12 min-[1024px]:top-12 min-[1024px]:size-16"
        >
          <path d="M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z" />
        </svg>
        <div aria-hidden="true" className="hidden self-start rounded-full bg-sheet p-3 min-[1024px]:block">
          <Mascot pose="vui" size="lg" />
        </div>
      </aside>
      <main className="flex flex-1 items-start justify-center px-4 pt-8 pb-12 min-[1024px]:col-span-7 min-[1024px]:items-center min-[1024px]:py-12">
        <div className="w-full max-w-[400px] min-w-0 rounded-sheet border border-line bg-sheet p-6 min-[641px]:p-8">
          <h1 className="m-0 font-display text-verdict text-balance">{title}</h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
