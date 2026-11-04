/**
 * V7 (04/11): in front of a subject's name, a small notebook with a pink spine and the name's
 * first letter, in place of a plain colour block. Decoration (aria-hidden); the name is beside it.
 */
export function SubjectMark({ name, className = "" }: { name: string; className?: string }) {
  const letter = Array.from(name.trim())[0]?.toLocaleUpperCase("vi") ?? "?";
  return (
    <span
      aria-hidden="true"
      data-subject-mark
      className={`inline-flex size-9 shrink-0 items-center justify-center rounded-control bg-hong-tint font-display text-body font-semibold leading-none text-hong ${className}`}
    >
      {letter}
    </span>
  );
}
