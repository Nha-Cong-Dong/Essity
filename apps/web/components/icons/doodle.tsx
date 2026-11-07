import { DOODLES, type DoodleElement, type DoodleName } from "./doodle-data";

export type { DoodleName };
export const DOODLE_NAMES = Object.keys(DOODLES) as DoodleName[];

/** 16/20/24 use the "-24" art (stroke 4 on a 48 grid); 48/64 use the finer 48px art (stroke 3). */
export type DoodleSize = 16 | 20 | 24 | 48 | 64;

const VIEW = "0 0 48 48";

/**
 * A hand-drawn icon (DESIGN-V5). Inline SVG, drawn in `currentColor`, so colour comes from the
 * parent's text colour. Decorative by default (`aria-hidden`); pass `title` to make it an image.
 * The art has no ids, so many copies on one page never clash.
 */
export function Doodle({
  name,
  size = 24,
  title,
  className,
}: {
  name: DoodleName;
  size?: DoodleSize;
  title?: string;
  className?: string;
}) {
  const art = DOODLES[name];
  const els: readonly DoodleElement[] = size >= 48 ? art.big : art.small;
  const strokeWidth = size >= 48 ? 3 : 4;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={VIEW}
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      data-doodle={name}
      className={className}
      {...(title ? { role: "img", "aria-label": title } : { "aria-hidden": true })}
    >
      {els.map(([tag, attrs], i) => {
        const props = { ...attrs, key: i };
        return tag === "circle" ? <circle {...props} /> : <path {...props} />;
      })}
    </svg>
  );
}
