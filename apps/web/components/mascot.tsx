import { cn } from "@/lib/utils";

// Phase B (04/11): "Bé Trang", a smiling notebook page with a pencil for hair. One mascot per
// screen at most, only in empty, preparing, locked and celebrating states; never on the answer,
// grading or source screens. Decoration: aria-hidden, the words always carry the meaning. Colours
// are tokens only (fill-*, stroke-*), so dark mode follows.

export type MascotPose = "vui" | "cho" | "chuanbi" | "chucmung";
const SIZES = { sm: "size-24", md: "size-36", lg: "size-48" } as const;

function Face({ pose }: { pose: MascotPose }) {
  const eye = "fill-ink";
  const line = "fill-none stroke-ink stroke-[2.5] [stroke-linecap:round]";
  return (
    <>
      <circle cx="42" cy="62" r="5.5" className="fill-rose-200" opacity=".8" />
      <circle cx="78" cy="62" r="5.5" className="fill-rose-200" opacity=".8" />
      {pose === "vui" || pose === "chucmung" ? (
        <>
          <path d="M42 54 q5 -7 10 0" className={line} />
          <path d="M68 54 q5 -7 10 0" className={line} />
        </>
      ) : pose === "cho" ? (
        <>
          <circle cx="48" cy="54" r="3.5" className={eye} />
          <circle cx="74" cy="54" r="3.5" className={eye} />
        </>
      ) : (
        <>
          <circle cx="47" cy="55" r="3.5" className={eye} />
          <circle cx="73" cy="55" r="3.5" className={eye} />
        </>
      )}
      {pose === "vui" && <path d="M50 66 q10 11 20 0" className={line} />}
      {pose === "chucmung" && <path d="M50 65 q10 14 20 0 z" className="fill-ink stroke-ink stroke-2 [stroke-linejoin:round]" />}
      {pose === "cho" && <path d="M54 70 h12" className={line} />}
      {pose === "chuanbi" && <path d="M52 69 q8 4 16 0" className={line} />}
    </>
  );
}

function Props({ pose }: { pose: MascotPose }) {
  const star = "fill-hong";
  if (pose === "vui")
    return (
      <>
        <path d="M18 40 l2 6 6 2 -6 2 -2 6 -2 -6 -6 -2 6 -2z" className={star} />
        <path d="M104 30 l1.6 5 5 1.6 -5 1.6 -1.6 5 -1.6 -5 -5 -1.6 5 -1.6z" className={star} />
        <path d="M24 78 l-14 -12 M96 78 l14 -12" className="stroke-ink fill-none stroke-[3] [stroke-linecap:round]" />
      </>
    );
  if (pose === "cho")
    return (
      <>
        <rect x="46" y="76" width="28" height="22" rx="7" className="fill-hong" />
        <path d="M52 76 v-6 a8 8 0 0 1 16 0 v6" className="fill-none stroke-hong stroke-[4]" />
        <circle cx="60" cy="87" r="3" className="fill-on-hong" />
        <circle cx="96" cy="30" r="2.5" className="fill-rose-300" />
        <circle cx="106" cy="40" r="2" className="fill-rose-300" />
        <circle cx="88" cy="22" r="2" className="fill-rose-300" />
      </>
    );
  if (pose === "chuanbi")
    return (
      <>
        <path d="M30 100 h60" className="stroke-line-strong stroke-[2] [stroke-linecap:round]" />
        <path d="M78 98 l16 -22 5 3 -16 22z" className="fill-pencil" />
        <circle cx="26" cy="30" r="2.5" className="fill-rose-300 m-dot" />
        <circle cx="36" cy="24" r="2.5" className="fill-rose-300 m-dot" />
        <circle cx="46" cy="30" r="2.5" className="fill-rose-300 m-dot" />
      </>
    );
  return (
    <>
      <path d="M60 4 v8 M22 16 l6 6 M98 16 l-6 6 M10 40 h8 M102 40 h8" className="stroke-hong fill-none stroke-[3] [stroke-linecap:round]" />
      <path d="M22 90 l-12 -34 M98 90 l12 -34" className="stroke-ink fill-none stroke-[3] [stroke-linecap:round]" />
      <path d="M100 8 l1.6 5 5 1.6 -5 1.6 -1.6 5 -1.6 -5 -5 -1.6 5 -1.6z" className={star} />
    </>
  );
}

export function Mascot({
  pose,
  size = "md",
  className,
}: {
  pose: MascotPose;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-mascot={pose}
      viewBox="0 0 120 120"
      className={cn("shrink-0", SIZES[size], className)}
    >
      <ellipse cx="60" cy="110" rx="30" ry="5" className="fill-rose-100" />
      <g transform={pose === "chucmung" ? "rotate(-8 60 60)" : "rotate(-4 60 60)"}>
        <path d="M60 22 q-4 -12 4 -18 l4 3 q-6 6 -2 15z" className="fill-pencil" />
        <path
          d="M30 24 h42 l22 22 v50 a8 8 0 0 1 -8 8 h-56 a8 8 0 0 1 -8 -8 v-64 a8 8 0 0 1 8 -8z"
          className="fill-sheet stroke-hong stroke-[3] [stroke-linejoin:round]"
        />
        <path d="M72 24 v16 a6 6 0 0 0 6 6 h16z" className="fill-rose-100 stroke-hong stroke-[3] [stroke-linejoin:round]" />
        <Face pose={pose} />
      </g>
      <Props pose={pose} />
    </svg>
  );
}
