// Small looping illustrations for "Hướng dẫn học" (CSS keyframes in globals.css, `guide-*`). Decoration only:
// aria-hidden. Under prefers-reduced-motion the keyframes are off and each drawing shows its final state.

const FRAME = "h-28 w-full max-w-56 shrink-0 min-[560px]:h-32";

export function GuideArt({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 224 128" aria-hidden="true" focusable="false" className={FRAME}>
      <rect x="4" y="4" width="216" height="120" rx="14" fill="var(--sheet)" stroke="var(--line)" strokeWidth="2" />
      {step === 0 && (
        <>
          <rect x="20" y="22" width="90" height="10" rx="5" fill="var(--sunken)" />
          <rect x="20" y="44" width="150" height="8" rx="4" fill="var(--sunken)" />
          <rect x="20" y="60" width="120" height="8" rx="4" fill="var(--sunken)" />
          <g className="guide-press">
            <rect x="20" y="86" width="84" height="24" rx="12" fill="var(--hong)" />
            <rect x="44" y="95" width="36" height="6" rx="3" fill="var(--on-hong, #fff)" />
          </g>
          <circle className="guide-ring" cx="62" cy="98" r="14" fill="none" stroke="var(--hong)" strokeWidth="2" />
        </>
      )}
      {step === 1 && (
        <>
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <rect x="20" y={20 + i * 32} width="184" height="24" rx="8" fill="var(--sunken)" />
              <rect x="34" y={29 + i * 32} width={90 - i * 14} height="6" rx="3" fill="var(--ink-soft)" />
            </g>
          ))}
          <rect className="guide-hop" x="20" y="20" width="184" height="24" rx="8" fill="none" stroke="var(--cam)" strokeWidth="3" />
        </>
      )}
      {step === 2 && (
        <>
          <rect x="20" y="18" width="184" height="58" rx="8" fill="var(--sunken)" />
          <rect className="guide-type" x="30" y="28" width="150" height="6" rx="3" fill="var(--ink-soft)" />
          <rect className="guide-type guide-type-2" x="30" y="42" width="120" height="6" rx="3" fill="var(--ink-soft)" />
          <rect className="guide-type guide-type-3" x="30" y="56" width="90" height="6" rx="3" fill="var(--ink-soft)" />
          <g className="guide-press guide-press-late">
            <rect x="120" y="88" width="84" height="24" rx="12" fill="var(--hong)" />
            <rect x="144" y="97" width="36" height="6" rx="3" fill="var(--on-hong, #fff)" />
          </g>
          <rect x="20" y="92" width="22" height="16" rx="4" fill="none" stroke="var(--ink-soft)" strokeWidth="2" />
        </>
      )}
      {step === 3 && (
        <>
          <rect x="20" y="22" width="120" height="8" rx="4" fill="var(--sunken)" />
          <rect x="20" y="40" width="90" height="8" rx="4" fill="var(--sunken)" />
          <g className="guide-press">
            <rect x="20" y="82" width="104" height="26" rx="13" fill="var(--hong)" />
            <rect x="46" y="92" width="52" height="6" rx="3" fill="var(--on-hong, #fff)" />
          </g>
          <g className="guide-pop">
            <circle cx="176" cy="64" r="22" fill="var(--hong-tint, #f9e6ee)" />
            <path d="M165 64l8 8 14-16" fill="none" stroke="var(--hong)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        </>
      )}
      {step === 4 && (
        <>
          <rect x="120" y="58" width="88" height="52" rx="10" fill="var(--sunken)" stroke="var(--line-strong)" strokeWidth="2" />
          <rect x="132" y="50" width="64" height="12" rx="4" fill="var(--line)" />
          {[0, 1, 2].map((i) => (
            <rect key={i} className={`guide-card guide-card-${i}`} x="28" y="22" width="52" height="34" rx="6" fill="var(--hong-tint, #f9e6ee)" stroke="var(--hong)" strokeWidth="2" />
          ))}
        </>
      )}
    </svg>
  );
}
