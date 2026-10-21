import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

// DESIGN.md §6.4: the question level (Nhận biết / Vận dụng / Vận dụng cao) is one rounded pill
// with a `--line` border. All three levels look the same: a level is not a score. Results are
// shown by VerdictMark (shape + word + colour), never by a coloured badge.
const badgeVariants = cva(
  "inline-flex h-8 w-fit shrink-0 items-center gap-2 whitespace-nowrap rounded-full border border-line bg-sheet px-3.5 text-small font-medium text-ink",
  {
    variants: {
      variant: {
        level: "",
      },
    },
    defaultVariants: {
      variant: "level",
    },
  }
)

function Badge({
  className,
  variant = "level",
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
