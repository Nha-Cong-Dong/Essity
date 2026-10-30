import * as React from "react"
import { cn } from "@/lib/utils"

// T9.10a: a chip that is a real checkbox. On: `--rose-100` ground, ink text, `--line-strong`
// border and a written tick, so the state never rests on the ground colour alone (it is a faint
// step from `--sheet`). Off: `--sheet` ground, same border. 44px tall.
type FilterChipProps = Omit<React.ComponentProps<"input">, "type" | "onChange"> & {
  onCheckedChange: (checked: boolean) => void
}

function FilterChip({ className, children, checked, onCheckedChange, ...props }: FilterChipProps) {
  return (
    <label
      data-slot="filter-chip"
      data-checked={checked ? "true" : "false"}
      className={cn(
        "inline-flex h-11 min-w-0 cursor-pointer items-center gap-2 rounded-control border border-line-strong px-3 text-caption text-ink transition-colors hover:border-ink-soft has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus has-[:disabled]:cursor-not-allowed has-[:disabled]:text-ink-soft motion-reduce:transition-none forced-colors:border-[ButtonText]",
        checked ? "bg-hong-tint" : "bg-sheet",
        className
      )}
    >
      <input
        type="checkbox"
        className="sr-only"
        checked={checked}
        onChange={(e) => onCheckedChange(e.target.checked)}
        {...props}
      />
      <span aria-hidden="true" className="w-3 shrink-0 text-center font-semibold">
        {checked ? "✓" : ""}
      </span>
      <span className="min-w-0 wrap-anywhere">{children}</span>
    </label>
  )
}

export { FilterChip }
