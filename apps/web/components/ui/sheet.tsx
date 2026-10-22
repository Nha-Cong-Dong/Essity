import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

// Design system v3.1 §4.3, in place of shadcn's Card.
// - sheet: a notebook page, a confirmation card, a book label.
// - over: menus, the source panel, the page in the focus frame.
// - sunken: "Vì sao câu này?", skeletons.
// - tile: a bento cell. tone="rose" for a secondary tile with an action; tone="hong" for the one
//   pink tile a screen may have (today's session, session done), on the solid pink surface.
const sheetVariants = cva("", {
  variants: {
    variant: {
      sheet: "rounded-sheet bg-sheet p-6 shadow-sheet sm:p-8",
      over: "rounded-sheet bg-raised px-2 py-2 shadow-over sm:px-8 sm:py-8",
      sunken: "rounded-sheet bg-sunken p-4 sm:p-6",
      tile: "rounded-tile bg-sheet p-6 shadow-sheet min-[901px]:p-8",
    },
    tone: {
      plain: "",
      rose: "",
      hong: "",
    },
  },
  compoundVariants: [
    { variant: "tile", tone: "rose", className: "bg-rose-100 shadow-none hover:shadow-sheet" },
    {
      variant: "tile",
      tone: "hong",
      className: "p-10 shadow-[0_30px_60px_-30px_rgb(110_23_62/0.55)] min-[901px]:p-11",
    },
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
