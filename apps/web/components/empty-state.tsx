import type { ReactNode } from "react";

import { Mascot, type MascotPose } from "@/components/mascot";
import { cn } from "@/lib/utils";

/**
 * The one empty state (UI-1b, direction rule 5): a sentence in lead size, one softer sentence
 * under it, at most one action. Never a bigger "value" size, never two buttons.
 */
export function EmptyState({
  title,
  hint,
  action,
  mascot,
  mascotKind,
  className,
}: {
  title: ReactNode;
  hint?: ReactNode;
  /** The one action: a Button or a link. */
  action?: ReactNode;
  /** Phase B: the mascot beside the words (above them on a phone). Words always stay. */
  mascot?: MascotPose;
  /** Cloud (default) = the assistant; "sun" = the encourager (praise, done). */
  mascotKind?: "cloud" | "sun";
  className?: string;
}) {
  return (
    <div
      data-slot="empty-state"
      className={cn("flex flex-col items-start gap-2", mascot && "gap-4 sm:flex-row sm:items-center sm:gap-6", className)}
    >
      {mascot ? <Mascot kind={mascotKind} pose={mascot} /> : null}
      <div className="flex flex-col items-start gap-2">
        <p className="m-0 text-lead">{title}</p>
        {hint ? <p className="m-0 text-body text-ink-soft">{hint}</p> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </div>
  );
}
