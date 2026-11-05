import { MASCOT_ART, type MascotArt } from "@/components/mascot-art";
import { cn } from "@/lib/utils";

// MASCOT-V2: the mascot is a magician cloud (top hat, glasses, a wizard's beard) with a die-cut white
// edge, so one art reads on the page, on solid pink and on the field. Five poses and a glyph, art from
// .work/DESIGN-V5/mascot/.
// At most one per screen, only in empty, preparing, locked and celebrating states; never on the
// answer, grading or source screens. Decoration: aria-hidden, the words always carry the meaning.
// The outline and the one teal detail follow the surface: `tone="solid"` is for solid pink, the
// field or any dark surface (outline #441125, teal #70c8cd); the default follows the page mode.

/** chao (waving), khen (cheering), nghi (thinking), cho (waiting), rong (empty, holding a card), glyph.
 * The first phase's names stay: vui = chao, chucmung = khen, chuanbi = nghi. */
export type MascotPose = "chao" | "khen" | "nghi" | "cho" | "rong" | "glyph" | "vui" | "chucmung" | "chuanbi";
const ART: Record<MascotPose, MascotArt> = {
  chao: "chao",
  vui: "chao",
  khen: "khen",
  chucmung: "khen",
  nghi: "nghi",
  chuanbi: "nghi",
  cho: "cho",
  rong: "rong",
  glyph: "glyph",
};
const SIZES = { sm: "size-24", md: "size-36", lg: "size-48" } as const;
const SOLID = { "--mascot-line": "#441125", "--mascot-teal": "#70c8cd" } as React.CSSProperties;

export function Mascot({
  pose,
  size = "md",
  tone = "page",
  className,
}: {
  pose: MascotPose;
  size?: keyof typeof SIZES;
  tone?: "page" | "solid";
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-mascot={pose}
      viewBox="0 0 200 200"
      className={cn("shrink-0", SIZES[size], className)}
      style={tone === "solid" ? SOLID : undefined}
    >
      {MASCOT_ART[ART[pose]]}
    </svg>
  );
}
