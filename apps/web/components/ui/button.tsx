import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

// Design system v3.1 (docs/plans/design-architecture-final.md §4.1): pills, four kinds, no more.
// - primary: at most one per screen. Bắt đầu, Gửi, Câu tiếp...
// - secondary: Ôn thêm, Ghi buổi học, Thực ra tôi đúng / sai, Gửi lại...
// - quiet: text only, for one-tap actions that must not shout: Không nhớ, Dừng tại đây,
//   Chấm sai, Bỏ câu này, Sửa bằng một câu.
// - primary-inverse: the primary button on a pink surface ([data-surface="hong"]).
// No destructive variant: nothing in the app is red. A disabled button is sunken, never faded
// with opacity, so its label keeps its contrast.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap no-underline select-none font-sans text-body font-semibold leading-none transition-[background-color,box-shadow,transform,color] duration-(--dur-ui) ease-out focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-focus active:scale-[0.97] active:duration-(--dur-press) disabled:pointer-events-none disabled:translate-y-0 disabled:scale-100 disabled:shadow-none [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "rounded-full bg-hong px-6 text-on-hong hover:-translate-y-px hover:bg-[color-mix(in_oklab,var(--hong)_88%,var(--ink))] hover:shadow-hong disabled:bg-sunken disabled:text-ink-soft",
        secondary:
          "rounded-full bg-transparent px-6 text-ink inset-ring-[1.5px] inset-ring-line-strong hover:bg-sunken disabled:bg-sunken disabled:text-ink-soft disabled:inset-ring-line",
        quiet:
          "h-11 rounded-control px-3 font-medium text-ink underline decoration-line-strong decoration-[1.5px] underline-offset-[5px] hover:decoration-ink disabled:text-ink-soft disabled:no-underline",
        "primary-inverse":
          "rounded-full bg-on-hong px-6 text-hong hover:-translate-y-px hover:shadow-[0_12px_28px_-12px_rgb(0_0_0/0.45)] disabled:bg-sunken disabled:text-ink-soft",
      },
      size: {
        md: "",
        lg: "",
      },
    },
    compoundVariants: [
      { variant: ["primary", "secondary"], size: "md", className: "h-13" },
      { variant: ["primary", "secondary", "primary-inverse"], size: "lg", className: "h-15 text-read" },
      { variant: "primary-inverse", size: "md", className: "h-15 text-read" },
    ],
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
)

type ButtonProps = ButtonPrimitive.Props &
  VariantProps<typeof buttonVariants> & {
    /** Waiting for an answer: a spinner, `aria-busy`, and no second press. */
    pending?: boolean
  }

function Button({ className, variant = "primary", size = "md", pending = false, disabled, children, ...props }: ButtonProps) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      {...props}
    >
      {pending ? (
        <span
          aria-hidden="true"
          className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
        />
      ) : null}
      {children}
    </ButtonPrimitive>
  )
}

export { Button, buttonVariants }
