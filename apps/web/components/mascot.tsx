import { MASCOT_ART, type MascotArt, type MascotKind } from "@/components/mascot-art";
import { cn } from "@/lib/utils";

// MASCOT-V3: two mascots, each with a die-cut white edge (one art reads on the page, solid pink and the
// field), five poses and a glyph.
// - kind="cloud" (default): the magician cloud, the ASSISTANT: header glyph, suggestions, guides, waiting,
//   thinking and the empty states inside the app.
// - kind="sun": the pink sun, the ENCOURAGER: the praise pop-up after a session, "Xong phần ôn hôm nay",
//   the sign-in screens.
// One mascot per screen, never both; only in empty, preparing, locked and celebrating states, never on the
// answer, grading or source screens. Decoration: aria-hidden, the words always carry the meaning.
// The outline and the one teal detail follow the surface: `tone="solid"` is for solid pink, the field or
// any dark surface (outline #441125, teal #70c8cd); the default follows the page mode.

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
  kind = "cloud",
  pose,
  size = "md",
  tone = "page",
  className,
}: {
  kind?: MascotKind;
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
      data-mascot-kind={kind}
      viewBox="0 0 200 200"
      className={cn("shrink-0", SIZES[size], className)}
      style={tone === "solid" ? SOLID : undefined}
    >
      {MASCOT_ART[kind][ART[pose]]}
    </svg>
  );
}
