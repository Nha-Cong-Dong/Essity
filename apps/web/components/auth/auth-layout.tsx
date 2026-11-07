import type { ReactNode } from "react";

import { Mascot } from "@/components/mascot";

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
    <div className="relative grid min-h-dvh grid-cols-1 bg-bg text-ink min-[1024px]:grid-cols-[1fr_1.1fr]">
      {/* Left/top: plum field */}
      <aside
        className="relative flex min-h-[214px] flex-col gap-5.5 bg-plum px-4.5 py-4 text-on-plum min-[1024px]:min-h-0 min-[1024px]:items-start min-[1024px]:justify-start min-[1024px]:px-10 min-[1024px]:py-10"
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
          <p className="relative z-[1] m-0 mt-1 max-w-[11ch] font-display text-title">
            {greeting}
          </p>
        )}

        {/* Desktop: mascot centred in the field, the bubble sits against its shoulder */}
        <div className="pointer-events-none absolute inset-0 z-[1] hidden items-center justify-center min-[1024px]:flex" aria-hidden="true">
          <div className="relative">
            <Mascot kind="sun" pose="chao" size="lg" className="size-60 drop-shadow-[0_10px_18px_rgba(0,0,0,0.3)]" />
            {bubble && (
              <div className="absolute -top-2 left-[calc(100%-36px)] z-[2] whitespace-nowrap rounded-slip bg-sheet px-4 py-3 font-display text-body font-semibold text-rose-900">
                {bubble}
              </div>
            )}
          </div>
        </div>

        {/* Mobile: mascot at the bottom right of the field, the bubble right beside it */}
        <div className="pointer-events-none absolute inset-0 z-[1] min-[1024px]:hidden" aria-hidden="true">
          <div className="absolute -bottom-[30px] right-2 flex items-end">
            {bubble && (
              <div className="mb-14 -mr-5 whitespace-nowrap rounded-slip bg-sheet px-3.5 py-2 font-display text-meta font-semibold text-rose-900">
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

        <div className="relative z-[1] w-full max-w-[440px] rounded-sheet border border-line bg-sheet px-6 py-10 min-[641px]:px-9">
          <h1 className="m-0 font-display text-verdict text-balance">{title}</h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
