import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

// DESIGN.md §7 and the canvas Controls artboard: three kinds, no more.
// - primary: at most one per screen (§2.1). Bắt đầu, Gửi, Câu tiếp...
// - secondary: Ôn thêm, Thực ra tôi đúng / sai, Gửi lại...
// - quiet: text only, for one-tap actions that must not shout: Không nhớ, Dừng tại đây,
//   Chấm sai, Bỏ câu này, Sửa bằng một câu.
// No destructive variant: nothing in the app is red (§2.3).
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap no-underline select-none font-sans text-body font-semibold leading-none transition-colors disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "h-13 rounded-sm border border-transparent bg-hong px-6 text-on-hong hover:bg-[color-mix(in_oklab,var(--hong)_86%,var(--ink))]",
        secondary:
          "h-13 rounded-sm border border-ink-soft bg-sheet px-6 text-ink hover:border-ink hover:bg-subtle",
        quiet:
          "h-11 rounded-sm px-3 font-medium text-ink underline decoration-line decoration-[1.5px] underline-offset-[5px] hover:decoration-ink",
      },
    },
    defaultVariants: {
      variant: "primary",
    },
  }
)

function Button({
  className,
  variant = "primary",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
