import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * The one empty state (UI-1b, direction rule 5): a sentence in lead size, one softer sentence
 * under it, at most one action. Never a bigger "value" size, never two buttons.
 */
export function EmptyState({
  title,
  hint,
  action,
  className,
}: {
  title: ReactNode;
  hint?: ReactNode;
  /** The one action: a Button or a link. */
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div data-slot="empty-state" className={cn("flex flex-col items-start gap-2", className)}>
      <p className="m-0 text-lead">{title}</p>
      {hint ? <p className="m-0 text-body text-ink-soft">{hint}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
