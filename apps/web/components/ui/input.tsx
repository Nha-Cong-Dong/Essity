import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

// Canvas Controls artboard: 52px, 8px radius, `--ink-soft` border (3:1). An invalid field gets a
// 2px `--partial` border, never red; pair it with a message (FieldError) that says what to do.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-13 w-full min-w-0 rounded-sm border border-ink-soft bg-sheet px-4 font-sans text-body text-ink outline-none transition-colors placeholder:text-ink-soft disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-2 aria-invalid:border-partial",
        className
      )}
      {...props}
    />
  )
}

export { Input }
