import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

// Design system v3.2 (V22), after the landing: flat, no shadow.
// - sheet / tile: a white card with a 1px line, r24: forms, a long list, a bento cell.
//   tone="rose" or tone="hong": the --hong-tint tile of the landing's "nx" lists (r24, no border);
//   put an NxList in it. At most one per screen region.
// - over: menus, the source panel, the page in the focus frame (the only shadow of the app).
// - sunken: "Vì sao câu này?", skeletons.
const sheetVariants = cva("", {
  variants: {
    variant: {
      sheet: "rounded-tile border border-line bg-sheet p-4 sm:p-6",
      over: "rounded-sheet bg-raised px-2 py-2 shadow-over sm:px-8 sm:py-8",
      sunken: "rounded-tile bg-sunken p-4 sm:p-5",
      tile: "rounded-tile border border-line bg-sheet p-4 min-[901px]:p-6",
    },
    tone: {
      plain: "",
      rose: "",
      hong: "",
    },
  },
  compoundVariants: [
    { variant: ["sheet", "tile"], tone: ["rose", "hong"], className: "border-transparent bg-hong-tint" },
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
