import type { ReactNode } from "react";

import { Mascot } from "@/components/mascot";

// V4 AUTH (06/11): split layout with plum field (left/top) + form card (right/bottom).
// Field shows mascot + bubble + dots + sticker chain. Form card has dots fading from edge.
// Login: sun mascot "Thật vui khi được gặp bạn" + bubble "Vào ôn thôi!"
// Register: sun mascot "Chào mừng bạn mới!" + bubble "Bắt đầu nhé"

const STAR_PATH = "M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z";

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
      {/* Sticker chain */}
      <svg className="pointer-events-none absolute left-[35%] top-[34px] z-[3] hidden h-16 w-16 rotate-[8deg] min-[1024px]:block" viewBox="0 0 100 100" aria-hidden="true">
        <path d={STAR_PATH} fill="#fff" stroke="#fff" strokeWidth="2" strokeLinejoin="round" />
      </svg>
      <svg className="pointer-events-none absolute left-[43.5%] top-[88px] z-[3] hidden h-11 w-11 rotate-[26deg] min-[1024px]:block" viewBox="0 0 100 100" aria-hidden="true">
        <path d={STAR_PATH} fill="var(--accent-bright)" stroke="var(--accent-bright)" strokeWidth="2" strokeLinejoin="round" />
      </svg>
      <svg className="pointer-events-none absolute left-[51.5%] top-[56px] z-[3] hidden h-[30px] w-[30px] rotate-[44deg] min-[1024px]:block" viewBox="0 0 100 100" aria-hidden="true">
        <path d={STAR_PATH} fill="var(--rose-300)" stroke="var(--rose-900)" strokeWidth="4" strokeLinejoin="round" />
      </svg>
      <svg className="pointer-events-none absolute left-[58%] top-[28px] z-[3] hidden h-5 w-5 rotate-[62deg] min-[1024px]:block" viewBox="0 0 100 100" aria-hidden="true">
        <path d={STAR_PATH} fill="var(--rose-300)" stroke="var(--rose-900)" strokeWidth="5" strokeLinejoin="round" />
      </svg>

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
          <p className="relative z-[1] m-0 mt-1 max-w-[11ch] font-display text-[26px] leading-[1.1] min-[1024px]:text-[32px] min-[1024px]:leading-[1.05]">
            {greeting}
          </p>
        )}

        {/* Mascot stage */}
        <div className="pointer-events-none absolute inset-0 z-[1] hidden min-[1024px]:block" aria-hidden="true">
          <div className="relative mx-auto h-full w-[340px]">
            <div className="absolute left-1/2 top-[26px] -ml-[170px] w-[340px] origin-[50%_90%]">
              <Mascot kind="sun" pose="chao" size="lg" className="drop-shadow-[0_10px_18px_rgba(0,0,0,0.3)]" />
            </div>
            {bubble && (
              <div className="absolute left-[calc(50%+112px)] top-5 z-[2] origin-[0_100%] whitespace-nowrap rounded-[18px_18px_18px_4px] bg-white px-4.5 py-3 font-display text-[17px] font-semibold leading-[1.2] text-rose-900 shadow-md">
                {bubble}
                <span className="absolute -left-[9px] bottom-0 h-4.5 w-4.5 bg-white [clip-path:polygon(100%_0,100%_100%,0_100%)]" />
              </div>
            )}
          </div>
        </div>

        {/* Mobile: mascot peeking from bottom right */}
        <div className="pointer-events-none absolute inset-0 z-[1] min-[1024px]:hidden" aria-hidden="true">
          <div className="absolute -bottom-[30px] right-1.5 w-[150px]">
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

        <div className="relative z-[1] w-full max-w-[440px] rounded-[28px] border border-line bg-sheet px-6 py-10 shadow-[0_1px_2px_rgb(102_23_56_/_0.05),0_10px_24px_-14px_rgb(102_23_56_/_0.14)] min-[641px]:px-9.5">
          <h1 className="m-0 font-display text-verdict text-balance">{title}</h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
