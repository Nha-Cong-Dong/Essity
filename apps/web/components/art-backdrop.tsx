// SHELL-ART: a static, low-contrast backdrop for the content area of AppShell: a 24px grid, dots
// every 96px and a few contour lines in two corners, all faded out toward the centre where text
// sits. Decoration only (aria-hidden, no pointer events, no motion). The layer is as tall as the
// page, its drawing is as tall as the window and sticks to it, so a long page does not stretch it.
// Colours are --art-grid / --art (globals.css), so light and dark follow the palette.

const CONTOUR_TR = [
  "M1200 40 C1110 50 1040 110 1010 190 C980 270 1010 330 1200 350",
  "M1200 90 C1135 100 1090 140 1070 200 C1050 260 1075 300 1200 310",
  "M1200 -10 C1080 -10 980 70 940 180 C900 290 960 400 1200 410",
  "M1200 140 C1160 150 1130 175 1125 210 C1120 245 1150 262 1200 264",
];
const CONTOUR_BL = [
  "M0 760 C90 750 170 690 200 610 C230 530 190 470 0 450",
  "M0 710 C65 700 110 660 130 600 C150 540 125 500 0 490",
  "M0 810 C120 810 220 730 260 620 C300 510 240 400 0 390",
  "M0 660 C40 650 70 625 75 590 C80 555 50 538 0 536",
];

export function ArtBackdrop() {
  return (
    <div aria-hidden="true" data-art="backdrop" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden min-[1024px]:left-(--rail-w)">
      <div
        className="sticky top-0 h-dvh w-full"
        style={{
          maskImage: "radial-gradient(ellipse 70% 65% at 50% 50%, transparent 30%, #000 85%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 65% at 50% 50%, transparent 30%, #000 85%)",
        }}
      >
        <svg className="absolute inset-0 size-full" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="art-grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M24 0H0V24" fill="none" stroke="var(--art-grid)" strokeWidth="1" />
            </pattern>
            <pattern id="art-dots" width="96" height="96" patternUnits="userSpaceOnUse">
              <circle cx="48" cy="48" r="1.5" fill="var(--art)" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#art-grid)" />
          <rect width="100%" height="100%" fill="url(#art-dots)" />
        </svg>
        <svg className="absolute inset-0 size-full" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
          <g fill="none" stroke="var(--art)" strokeWidth="1.25" strokeLinecap="round">
            {CONTOUR_TR.map((d) => (
              <path key={d} d={d} />
            ))}
            {CONTOUR_BL.map((d) => (
              <path key={d} d={d} />
            ))}
          </g>
        </svg>
      </div>
    </div>
  );
}
