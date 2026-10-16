import type { ReactNode } from "react";

/**
 * A form error (DESIGN.md §3.1): `--partial` + a triangle + a sentence that says what to do
 * ("Ngày thi phải sau hôm nay."). Never red. Give it an `id` and point the field's
 * `aria-describedby` at it, with `aria-invalid` on the field.
 */
export function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="m-0 flex items-center gap-2 text-small text-partial">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0">
        <path
          d="M8 1.75 14.5 13.5h-13z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 6.5v3.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r=".9" fill="currentColor" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

/** A hint under a field ("Ít nhất 8 ký tự. Không cần ký tự đặc biệt."). */
export function FieldHint({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="m-0 text-small text-ink-soft">
      {children}
    </p>
  );
}
