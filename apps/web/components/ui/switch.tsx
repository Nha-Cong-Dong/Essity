import * as React from "react"
import { cn } from "@/lib/utils"

// T9.10a: a two-state switch with its label beside it (role=switch, 44px tall). The state is
// written in words by the label, not only by the track: the knob moves and the track turns pink,
// but nothing relies on colour alone.
type SwitchProps = Omit<React.ComponentProps<"button">, "onChange" | "role" | "aria-checked"> & {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

function Switch({ checked, onCheckedChange, className, children, ...props }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      data-slot="switch"
      data-checked={checked}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "inline-flex h-11 min-w-0 items-center gap-3 rounded-control px-1 text-body text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:text-ink-soft forced-colors:border forced-colors:border-[ButtonText]",
        className
      )}
      {...props}
    >
      <span
        aria-hidden="true"
        className={cn(
          "relative h-7 w-12 shrink-0 rounded-full border border-line-strong transition-colors motion-reduce:transition-none",
          checked ? "bg-hong" : "bg-sheet"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 size-5.5 rounded-full border border-line-strong bg-sheet transition-[left] motion-reduce:transition-none",
            checked ? "left-5.5" : "left-0.5"
          )}
        />
      </span>
      <span className="min-w-0 text-left">{children}</span>
    </button>
  )
}

export { Switch }
