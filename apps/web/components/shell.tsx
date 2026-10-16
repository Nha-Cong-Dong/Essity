import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type ShellProps = {
  children: ReactNode;
  /** Wider column for screens that show a table or a chart (US-10). */
  wide?: boolean;
  className?: string;
};

/**
 * Page frame for "one screen, one task" (PRD §3, principle 2): a quiet header and a single
 * centred column. No sidebar, no secondary panels competing for attention.
 */
export function Shell({ children, wide = false, className }: ShellProps) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="px-6 py-4">
        <span className="text-sm font-semibold tracking-tight text-muted-foreground">Essity</span>
      </header>
      <main
        className={cn(
          "mx-auto flex w-full flex-1 flex-col gap-6 px-6 pb-16 pt-4",
          wide ? "max-w-4xl" : "max-w-xl",
          className,
        )}
      >
        {children}
      </main>
    </div>
  );
}
