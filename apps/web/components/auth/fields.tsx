"use client";

import { Eye, EyeOff } from "lucide-react";
import { type ComponentProps, type ReactNode, useState } from "react";

import { cn } from "@/lib/utils";

// Fields of the account screens (DESIGN.md §6.1, canvas Auth): printed Be Vietnam Pro 18px on a
// dotted line, which turns into a solid `--hong` line on focus and `--partial` when invalid.

const LINE_INPUT =
  "h-12 w-full rounded-none border-0 border-b-2 border-dotted border-ink-soft/70 bg-transparent px-0.5 font-sans text-[18px] leading-tight text-ink outline-none " +
  "focus-visible:border-solid focus-visible:border-hong focus-visible:shadow-[0_2px_0_0_var(--hong)] " +
  "aria-invalid:border-solid aria-invalid:border-partial";

type FieldProps = Omit<ComponentProps<"input">, "id"> & {
  id: string;
  label: string;
  /** Ids of the hint and error under the field. */
  describedBy?: string;
  invalid?: boolean;
  children?: ReactNode;
};

export function AuthField({ id, label, describedBy, invalid, className, children, ...props }: FieldProps) {
  return (
    <div className="relative flex flex-col gap-1.5">
      <label htmlFor={id} className="text-small font-semibold">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className={cn(LINE_INPUT, className)}
        {...props}
      />
      {children}
    </div>
  );
}

/** A password field with a show/hide button, which replaces "type it again" (DESIGN.md §6.1). */
export function PasswordField({ children, ...props }: Omit<FieldProps, "type">) {
  const [shown, setShown] = useState(false);
  const Icon = shown ? EyeOff : Eye;
  return (
    <AuthField {...props} type={shown ? "text" : "password"} className="pr-12">
      <button
        type="button"
        onClick={() => setShown(!shown)}
        aria-label={shown ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
        aria-pressed={shown}
        className="absolute top-[29px] right-0 inline-flex size-11 items-center justify-center rounded-full text-ink-soft hover:text-ink"
      >
        <Icon className="size-5" aria-hidden="true" />
      </button>
      {children}
    </AuthField>
  );
}

/** A `--partial` box above a form: rate limited, link expired... Never red. */
export function AuthNote({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="m-0 flex items-start gap-2.5 rounded-sm bg-[color-mix(in_srgb,var(--partial)_12%,var(--sheet))] px-4 py-3 text-[15px]"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="mt-1 shrink-0 text-partial">
        <path d="M8 1.75 14.5 13.5h-13z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M8 6.5v3.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r=".9" fill="currentColor" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

/** A text link of the account screens ("Quên mật khẩu?", "Đăng ký"). */
export const AUTH_LINK =
  "font-medium text-ink underline decoration-ink-soft decoration-[1.5px] underline-offset-4 hover:decoration-ink";
