import { Check, Clock, Mail, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// V4 (C1-AUTH-SUB-V4): one block for every "result" state of the account screens (link sent,
// verified, password saved, link expired, could not check). A round mark, one bold line, the
// explanation, then the actions. Never red: a problem is `--partial`, success is `--correct`.

const MARKS = {
  mail: { Icon: Mail, tone: "partial" },
  ok: { Icon: Check, tone: "correct" },
  expired: { Icon: Clock, tone: "partial" },
  warn: { Icon: TriangleAlert, tone: "partial" },
} as const;

export type AuthMark = keyof typeof MARKS;

export function AuthState({
  mark,
  title,
  children,
  actions,
  role,
  busy,
}: {
  mark: AuthMark;
  /** The one bold line ("Đã xác minh email."). */
  title: ReactNode;
  /** The explanation under it. */
  children?: ReactNode;
  actions?: ReactNode;
  role?: "status";
  busy?: boolean;
}) {
  const { Icon, tone } = MARKS[mark];
  return (
    <div className="flex flex-col gap-4" role={role} aria-busy={busy || undefined}>
      <span
        aria-hidden="true"
        data-auth-mark={mark}
        className={cn(
          "inline-flex size-12 items-center justify-center rounded-full",
          tone === "correct"
            ? "bg-[color-mix(in_srgb,var(--correct)_16%,var(--sheet))] text-correct"
            : "bg-[color-mix(in_srgb,var(--partial)_16%,var(--sheet))] text-partial",
        )}
      >
        <Icon className="size-6" strokeWidth={2} />
      </span>
      <p className="m-0 font-display text-lead font-semibold text-balance">{title}</p>
      {children}
      {actions && <div className="flex flex-col gap-3">{actions}</div>}
    </div>
  );
}

/** The explanation line of an AuthState. */
export function AuthBody({ children }: { children: ReactNode }) {
  return <p className="m-0 text-ink-soft">{children}</p>;
}
