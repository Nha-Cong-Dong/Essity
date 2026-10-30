import * as React from "react"
import { cn } from "@/lib/utils"

// Design system v3.1 §4.2: a native select drawn like Input (a box, `--line-strong` border, 52px,
// focus ring 2px away). Native on purpose: it works on every phone, with a keyboard and with a
// screen reader, and a long option wraps in the system's own list.
function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        "h-13 w-full min-w-0 rounded-control border border-line-strong bg-sheet px-4 font-sans text-body text-ink outline-none transition-colors hover:border-ink-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-soft",
        className
      )}
      {...props}
    />
  )
}

export { Select }
