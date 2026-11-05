"use client"

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

// DESIGN-V3: a modal on Base UI's Dialog, so focus is trapped inside, Escape and a click outside
// call onOpenChange(false), and the title and description name the dialog (aria-labelledby and
// aria-describedby). Focus returns to the opener on close.
// - default: a sheet-sized modal.
// - celebrate: the praise pop-up (after a study session): 440px max, the one overlay shadow
//   (--elev-over), content centred. It rises 12px and scales in over 260ms; under
//   prefers-reduced-motion it only fades (the transform classes are dropped, not slowed).
type DialogVariant = "default" | "celebrate"

type DialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  variant?: DialogVariant
  /** Anything drawn above the title, e.g. the mascot of a celebrate dialog. */
  media?: ReactNode
  children?: ReactNode
  className?: string
  /** Where to mount the dialog; the body by default. A preview uses it to keep a [data-tone] subtree. */
  container?: HTMLElement | null
}

function Dialog({ open, onOpenChange, title, description, variant = "default", media, children, className, container }: DialogProps) {
  const celebrate = variant === "celebrate"
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal container={container}>
        <DialogPrimitive.Backdrop
          data-slot="dialog-backdrop"
          className="fixed inset-0 z-(--z-scrim) bg-ink/40 transition-opacity duration-(--dur-ui) ease-out data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:duration-1"
        />
        <DialogPrimitive.Popup
          data-slot="dialog"
          data-variant={variant}
          className={cn(
            "fixed top-1/2 left-1/2 z-(--z-panel) w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-sheet bg-raised p-6 text-ink shadow-over outline-none sm:p-8",
            "transition-[opacity,transform] duration-(--dur-reveal) ease-(--ease-out)",
            "data-[ending-style]:opacity-0 data-[starting-style]:opacity-0",
            // Motion: a small rise and scale, only when the user has not asked for less.
            "motion-safe:data-[ending-style]:translate-y-[calc(-50%+8px)] motion-safe:data-[starting-style]:translate-y-[calc(-50%+12px)] motion-safe:data-[ending-style]:scale-[0.97] motion-safe:data-[starting-style]:scale-[0.96]",
            celebrate ? "max-w-[440px] text-center" : "max-w-[560px]",
            className,
          )}
        >
          {media ? <div className="mb-4 flex justify-center">{media}</div> : null}
          <DialogPrimitive.Title className="m-0 font-display text-lead text-balance">{title}</DialogPrimitive.Title>
          {description ? (
            <DialogPrimitive.Description className="m-0 mt-2 text-body text-ink-soft">{description}</DialogPrimitive.Description>
          ) : null}
          {children ? <div className="mt-6">{children}</div> : null}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export { Dialog }
export type { DialogProps, DialogVariant }
