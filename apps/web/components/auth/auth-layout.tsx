import type { ReactNode } from "react";

import { Mascot } from "@/components/mascot";

const STAR = "M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z";

/** The sticker chain of the mockup: one star shape, shrinking and turning toward the form. */
const CHAIN = [
  { cls: "left-[35%] top-[34px] w-16 rotate-[8deg] fill-on-plum stroke-on-plum", sw: 2 },
  { cls: "left-[43.5%] top-[88px] w-11 rotate-[26deg] fill-accent-bright stroke-accent-bright", sw: 2 },
  { cls: "left-[51.5%] top-14 w-[30px] rotate-[44deg] fill-rose-300 stroke-rose-900", sw: 4 },
  { cls: "left-[58%] top-7 w-5 rotate-[62deg] fill-rose-300 stroke-rose-900", sw: 5 },
] as const;

/** Words of the headline with the hand-drawn teal underline. */
export function Underlined({ children }: { children: ReactNode }) {
  return (
    <em className="relative inline-block not-italic">
      {children}
      <svg
        viewBox="0 0 320 18"
        preserveAspectRatio="none"
        aria-hidden="true"
        className="absolute -bottom-2 left-0 h-3.5 w-full fill-none stroke-accent-bright stroke-4 [stroke-linecap:round] min-[1024px]:-bottom-2.5"
      >
        <path d="M3 12 C 60 4, 130 15, 190 8 S 290 5, 317 10" />
      </svg>
    </em>
  );
}

// V4 AUTH (06/11): split layout with plum field (left/top) + form card (right/bottom).
// Field shows mascot + bubble + dots + sticker chain. Form card has dots fading from edge.
// Login: sun mascot "Thật vui khi được gặp bạn" + bubble "Vào ôn thôi!"
// Register: sun mascot "Chào mừng bạn mới!" + bubble "Bắt đầu nhé"

/** One account screen: plum field with mascot, form card on the right/bottom. */
export function AuthLayout({
  title,
  children,
  greeting,
  bubble,
}: {
  title: ReactNode;
  children: ReactNode;
  /** Text shown in the field header, e.g. "Thật vui khi được gặp bạn" */
  greeting?: ReactNode;
  /** Bubble text near mascot, e.g. "Vào ôn thôi!" */
  bubble?: string;
}) {
  return (
    <div className="relative grid min-h-dvh grid-cols-1 bg-bg text-ink min-[1024px]:grid-cols-2">
      {CHAIN.map((c, i) => (
        <svg
          key={i}
          data-sticker=""
          viewBox="0 0 100 100"
          aria-hidden="true"
          className={`pointer-events-none absolute z-[3] ${i < 2 ? "" : "hidden min-[1024px]:block"} ${c.cls} max-[1023px]:!left-auto ${i === 0 ? "max-[1023px]:!right-[22px] max-[1023px]:!top-4 max-[1023px]:!w-[34px]" : ""} ${i === 1 ? "max-[1023px]:!right-[66px] max-[1023px]:!top-9 max-[1023px]:!w-[22px]" : ""}`}
        >
          <path d={STAR} strokeWidth={c.sw} strokeLinejoin="round" />
        </svg>
      ))}
      <svg
        data-arrow=""
        viewBox="0 0 270 110"
        aria-hidden="true"
        className="pointer-events-none absolute left-[calc(25%+130px)] top-[50%] z-[3] hidden h-auto w-[calc(25%-146px)] fill-none stroke-accent-bright stroke-[3.4] [stroke-linecap:round] [stroke-linejoin:round] min-[1024px]:block"
      >
        <path d="M6 96 C 50 40, 110 20, 160 60 S 220 84, 252 34" />
        <path d="M232 30 L252 34 L248 54" />
      </svg>
      {/* Left/top: plum field */}
      <aside
        className="relative flex min-h-[214px] flex-col gap-5.5 bg-plum px-4.5 py-4 text-on-plum min-[1024px]:min-h-0 min-[1024px]:items-start min-[1024px]:justify-start min-[1024px]:px-12 min-[1024px]:py-10"
        data-tier="field"
      >
        {/* Dot pattern (white 18%, masked radial) */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18'%3E%3Ccircle cx='2.5' cy='2.5' r='1.7' fill='white' fill-opacity='.18'/%3E%3C/svg%3E")`,
            WebkitMaskImage: "radial-gradient(ellipse 80% 70% at 85% 85%, #000 0, transparent 75%)",
            maskImage: "radial-gradient(ellipse 80% 70% at 85% 85%, #000 0, transparent 75%)",
          }}
        />

        <a href="/" aria-label="Essity" className="relative z-[1] inline-flex min-h-11 items-center font-display text-logo text-on-plum no-underline">
          Essity
        </a>

        {greeting && (
          <p className="relative z-[1] m-0 mt-1 max-w-[11ch] font-display text-title font-semibold leading-[1.1] tracking-[-0.03em] min-[1024px]:mt-6 min-[1024px]:text-display min-[1024px]:leading-[1.04] [&>span]:block">
            {greeting}
          </p>
        )}

        {/* Desktop: mascot centred in the field, the bubble sits against its shoulder */}
        <div className="pointer-events-none absolute inset-0 z-[1] hidden items-center justify-center min-[1024px]:flex" aria-hidden="true">
          <div className="relative min-[1024px]:-translate-x-5 min-[1024px]:translate-y-24">
            <Mascot kind="sun" pose="chao" size="lg" className="size-[270px] drop-shadow-[0_10px_18px_rgba(0,0,0,0.3)]" />
            {bubble && (
              <div className="absolute -top-2 left-[calc(100%-36px)] z-[2] whitespace-nowrap rounded-slip bg-sheet px-4 py-3 font-display text-body font-semibold text-ink">
                {bubble}
              </div>
            )}
          </div>
        </div>

        {/* Mobile: mascot at the bottom right of the field, the bubble right beside it */}
        <div className="pointer-events-none absolute inset-0 z-[1] min-[1024px]:hidden" aria-hidden="true">
          <div className="absolute -bottom-[30px] right-2 flex items-end">
            {bubble && (
              <div className="mb-14 -mr-5 whitespace-nowrap rounded-slip bg-sheet px-3.5 py-2 font-display text-meta font-semibold text-ink">
                {bubble}
              </div>
            )}
            <Mascot kind="sun" pose="chao" size="md" />
          </div>
        </div>
      </aside>

      {/* Right/bottom: form card */}
      <main className="relative overflow-hidden bg-bg px-4 py-6.5 pb-11 min-[1024px]:flex min-[1024px]:items-center min-[1024px]:justify-center min-[1024px]:px-8 min-[1024px]:py-0">
        {/* Dot pattern on form side (rose-300, fading toward center) */}
        <div
          className="pointer-events-none absolute inset-0 hidden min-[1024px]:block"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18'%3E%3Ccircle cx='2.5' cy='2.5' r='1.7' fill='%23ffa8c6' fill-opacity='.4'/%3E%3C/svg%3E")`,
            WebkitMaskImage: "radial-gradient(ellipse 44% 40% at 50% 50%, transparent 55%, #000 100%)",
            maskImage: "radial-gradient(ellipse 44% 40% at 50% 50%, transparent 55%, #000 100%)",
          }}
        />

        <div className="relative z-[1] w-full max-w-[440px] rounded-sheet border border-line bg-sheet px-[22px] py-7 min-[641px]:px-[38px] min-[641px]:py-10">
          <h1 className="m-0 font-display text-verdict text-balance">{title}</h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
