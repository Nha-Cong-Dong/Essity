"use client";

import { Eye, EyeOff } from "lucide-react";
import { type ComponentProps, type ReactNode, useState } from "react";

import { Input } from "@/components/ui/input";

// Fields of the account screens. Forms are boxes, writing is ruled lines (design system v3.1
// §4.2, plan V4): each field is the shared Input, with its focus ring and its `--partial` border
// when invalid, never red.

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
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-meta font-semibold">
        {label}
      </label>
      <Input
        id={id}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className={className}
        {...props}
      />
      {children}
    </div>
  );
}

/** A password field with a show/hide button, which replaces "type it again" (DESIGN.md §6.1). */
export function PasswordField({ id, label, describedBy, invalid, children, ...props }: Omit<FieldProps, "type">) {
  const [shown, setShown] = useState(false);
  const Icon = shown ? EyeOff : Eye;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-meta font-semibold">
        {label}
      </label>
      {/* The eye sits in a box of its own around the input, so it stays centred on the field. */}
      <div className="relative">
        <Input
          id={id}
          type={shown ? "text" : "password"}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className="pr-13"
          {...props}
        />
        <button
          type="button"
          onClick={() => setShown(!shown)}
          aria-label={shown ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
          aria-pressed={shown}
          className="absolute inset-y-0 right-1 my-auto inline-flex size-11 items-center justify-center rounded-full text-ink-soft hover:text-ink"
        >
          <Icon className="size-5" aria-hidden="true" />
        </button>
      </div>
      {children}
    </div>
  );
}

/** A `--partial` box above a form: rate limited, link expired... Never red. */
export function AuthNote({ children }: { children: ReactNode }) {
  return (
    <p
      role="alert"
      className="m-0 flex items-start gap-2.5 rounded-control bg-[color-mix(in_srgb,var(--partial)_12%,var(--sheet))] px-4 py-3 text-body"
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
