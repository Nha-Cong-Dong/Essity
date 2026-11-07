import { cn } from "@/lib/utils";

/** The layered-E logo (LOGO-E). Colours come from --logo-ink / --logo-accent, so dark mode follows the theme. */
export function BrandMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      data-brand-mark=""
      className={cn("shrink-0", className)}
    >
      <rect x="12" y="10" width="10" height="44" rx="5" fill="var(--logo-ink)" />
      <rect x="12" y="10" width="40" height="10" rx="5" fill="var(--logo-ink)" />
      <rect x="28" y="27" width="24" height="10" rx="5" fill="var(--logo-accent)" />
      <rect x="12" y="44" width="40" height="10" rx="5" fill="var(--logo-ink)" />
    </svg>
  );
}
