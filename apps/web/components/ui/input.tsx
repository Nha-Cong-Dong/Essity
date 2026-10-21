import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

// Design system v3.1 §4.2: forms are boxes, writing is ruled lines (AnswerBox). 52px, radius 12,
// `--line-strong` border (3:1). Focus is a 2px ring 2px away: the base `:focus-visible` rule loses
// to utilities, so the ring is spelt out here. An invalid field gets a 2px `--partial` border,
// never red, paired with a FieldError that says what to do. Never put a box straight on the dark
// book cover (2.55:1): put it on a sheet.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-13 w-full min-w-0 rounded-control border border-line-strong bg-sheet px-4 font-sans text-body text-ink outline-none transition-colors placeholder:text-ink-soft hover:border-ink-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-soft aria-invalid:border-2 aria-invalid:border-partial",
        className
      )}
      {...props}
    />
  )
}

export { Input }
