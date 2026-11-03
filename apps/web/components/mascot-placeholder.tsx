/** Hackathon placeholder for the mascot art (drawn later): a soft round slot, hidden from readers. */
export function MascotPlaceholder({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-mascot="placeholder"
      className={`inline-flex size-16 shrink-0 items-center justify-center rounded-full bg-rose-100 text-lead ${className}`}
    >
      ✿
    </span>
  );
}
