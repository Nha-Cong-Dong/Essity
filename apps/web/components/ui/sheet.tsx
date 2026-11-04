import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

// Design system v3.2 (V22): three faces, flat, a hairline and no shadow.
// - sheet / tile: a white card with a 1px line, r16: forms, long lists, a bento cell.
//   tone="rose" or tone="hong": the "main sheet": --hong-tint, r24, no border; at most one per screen.
// - over: menus, the source panel, the page in the focus frame (the only shadow of the app).
// - sunken: "Vì sao câu này?", skeletons.
const sheetVariants = cva("", {
  variants: {
    variant: {
      sheet: "rounded-card border border-line bg-sheet p-5 sm:p-6",
      over: "rounded-sheet bg-raised px-2 py-2 shadow-over sm:px-8 sm:py-8",
      sunken: "rounded-card bg-sunken p-4 sm:p-5",
      tile: "rounded-card border border-line bg-sheet p-5 min-[901px]:p-6",
    },
    tone: {
      plain: "",
      rose: "",
      hong: "",
    },
  },
  compoundVariants: [
    { variant: ["sheet", "tile"], tone: ["rose", "hong"], className: "rounded-sheet border-transparent bg-hong-tint p-6 min-[901px]:p-10" },
  ],
  defaultVariants: {
    variant: "sheet",
    tone: "plain",
  },
})

function Sheet({
  className,
  variant,
  tone,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof sheetVariants>) {
  return (
    <div
      data-slot="sheet"
      data-surface={tone === "hong" ? "hong" : undefined}
      className={cn(sheetVariants({ variant, tone }), className)}
      {...props}
    />
  )
}

export { Sheet, sheetVariants }
