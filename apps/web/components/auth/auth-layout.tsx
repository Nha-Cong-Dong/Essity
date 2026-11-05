import type { ReactNode } from "react";

// V22 (04/11): every account screen is one plain card, 420px wide, centred on the page. The logo
// sits top left; no poster, no picture. The page title is the card's h1.

/** One account screen: the logo, then a card with the page title (h1) and the form. */
export function AuthLayout({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg text-ink">
      <header data-auth="top" className="flex h-16 items-center px-4 min-[1024px]:px-10">
        <a href="/" aria-label="Essity" className="inline-flex min-h-11 items-center font-display text-logo text-hong-text no-underline">
          Essity
        </a>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-6 pb-12 min-[1024px]:items-center min-[1024px]:pt-0">
        <div className="w-full max-w-[420px] min-w-0 rounded-sheet bg-sheet p-6 min-[641px]:border min-[641px]:border-line min-[641px]:p-8">
          <h1 className="m-0 font-display text-verdict text-balance">{title}</h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
