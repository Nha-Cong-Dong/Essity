import type { ReactNode } from "react";

// T1.24, approved mockup docs/design/screens-html/auth-v2. Every account screen: a pink poster
// column and a sheet with the form. Desktop is 5/7 two columns (logo, one big line, a small tilted
// notebook that is only a picture); under 1024px the poster is a 72px strip with the logo alone.
// Colours come from --poster / --on-poster (globals.css), which hold contrast in both palettes.
export const POSTER_LINE = "Tối nay ôn gì, đã có app lo.";

function PosterNotebook() {
  return (
    <div aria-hidden="true" className="hidden min-[1024px]:mt-auto min-[1024px]:block min-[1024px]:pl-10 [@media(max-height:640px)]:hidden">
      <div className="relative -mb-14 w-[330px] max-w-full origin-[20%_0] -rotate-[3.5deg] overflow-hidden rounded-cover-spine bg-sheet pr-[22px] pb-[90px] pl-[34px] text-ink shadow-[0_30px_60px_-20px_rgb(40_6_22/0.55)]">
        <i className="absolute inset-y-0 left-0 w-3.5 bg-spine" />
        <div className="flex items-baseline justify-between border-b border-line pt-4 pb-3">
          <b className="font-display text-lead leading-none">Hôm nay</b>
          <span className="text-meta text-ink-soft">thứ Tư, 4/11</span>
        </div>
        <p className="m-0 mt-[18px] font-display text-lead">Vì sao bầu trời có màu xanh?</p>
        <p
          className="m-0 mt-3 text-meta leading-7 text-ink-soft"
          style={{
            backgroundImage: "linear-gradient(transparent 27px, var(--line) 27px)",
            backgroundSize: "100% 28px",
          }}
        >
          Ánh sáng xanh bị không khí tán ra khắp bầu trời nhiều hơn các màu khác.
        </p>
        <p className="m-0 mt-3.5 inline-flex items-center gap-2 text-meta font-semibold">
          <i className="size-4 rounded-full bg-correct" />
          Đúng
        </p>
      </div>
    </div>
  );
}

/** One account screen: poster, then the sheet with the page title (h1) and the form. */
export function AuthLayout({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-sheet text-ink min-[1024px]:grid-cols-[5fr_7fr] min-[1024px]:grid-rows-[1fr]">
      <aside
        data-auth="poster"
        className="auth-poster relative isolate flex flex-col overflow-hidden text-on-poster min-[1024px]:min-h-dvh"
      >
        <div className="flex h-18 items-center px-4 min-[1024px]:h-24 min-[1024px]:px-10">
          <a
            href="/"
            aria-label="Essity"
            className="inline-flex min-h-11 items-center font-display text-logo text-on-poster no-underline"
          >
            Essity
          </a>
        </div>
        <div
          aria-hidden="true"
          className="auth-poster-grid pointer-events-none absolute inset-0 -z-10 hidden min-[1024px]:block"
        />
        <div className="hidden px-10 pt-6 min-[1024px]:block">
          <p className="m-0 max-w-[12ch] font-display text-[clamp(34px,3.4vw,52px)] leading-[1.1] font-semibold tracking-[-0.025em] text-balance">
            {POSTER_LINE}
          </p>
        </div>
        <PosterNotebook />
      </aside>
      <main className="flex items-start justify-center px-4 pt-7 pb-12 min-[1024px]:items-center min-[1024px]:px-16 min-[1024px]:py-12">
        <div className="w-full max-w-[400px] min-w-0">
          <h1 className="m-0 font-display text-verdict text-balance">
            {title}
          </h1>
          <div className="mt-6 flex flex-col gap-5">{children}</div>
        </div>
      </main>
    </div>
  );
}
