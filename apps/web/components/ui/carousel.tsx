"use client"

import { ArrowLeft, ArrowRight } from "lucide-react"
import { Children, useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from "react"

import { cn } from "@/lib/utils"

// DESIGN-V3 (Kho, by session): a horizontal band of cards. A scroll-snap track (x mandatory, gap 16),
// two round 44px buttons ("Thẻ trước" / "Thẻ sau", disabled at both ends), the position "3 / 12"
// and ←/→ while the track has focus. Each child is one slide: give it its own sheet; the slide is
// 380px wide (86vw on a phone) and the track aligns items to the top, so editing a card in place
// makes only that card taller. Scrolling is smooth unless the user asked for reduced motion.
// With touch or a trackpad the track scrolls by hand; the buttons and keys are the other ways in.
const GAP = 16

function smooth(): ScrollBehavior {
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  return reduce ? "auto" : "smooth"
}

type CarouselProps = {
  /** Names the region for assistive technology, e.g. "Thẻ của buổi học". */
  label: string
  children: ReactNode
  className?: string
}

function Carousel({ label, children, className }: CarouselProps) {
  const slides = Children.toArray(children)
  const count = slides.length
  const track = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(0)

  const step = useCallback(() => {
    const first = track.current?.firstElementChild as HTMLElement | null
    return first && first.offsetWidth > 0 ? first.offsetWidth + GAP : 0
  }, [])

  const go = useCallback(
    (to: number) => {
      const next = Math.min(count - 1, Math.max(0, to))
      setIndex(next)
      const el = track.current
      const slide = el?.children[next] as HTMLElement | undefined
      if (el && slide && typeof el.scrollTo === "function") {
        el.scrollTo({ left: slide.offsetLeft - el.offsetLeft, behavior: smooth() })
      }
    },
    [count],
  )

  const onScroll = useCallback(() => {
    const el = track.current
    const s = step()
    if (!el || s === 0) return
    setIndex(Math.min(count - 1, Math.max(0, Math.round(el.scrollLeft / s))))
  }, [count, step])

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return // arrows inside a slide's own field stay its own
    if (event.key === "ArrowRight") {
      event.preventDefault()
      go(index + 1)
    } else if (event.key === "ArrowLeft") {
      event.preventDefault()
      go(index - 1)
    }
  }

  const current = Math.min(index, Math.max(0, count - 1))
  const round =
    "inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-sheet text-ink inset-ring-[1.5px] inset-ring-line-strong transition-[background-color,transform] duration-(--dur-ui) hover:bg-sunken active:scale-[0.97] disabled:pointer-events-none disabled:bg-sunken disabled:text-ink-soft disabled:inset-ring-line focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus motion-reduce:transition-none"

  return (
    <div role="region" aria-label={label} data-slot="carousel" className={cn("flex min-w-0 flex-col gap-4", className)}>
      <div className="flex items-center justify-end gap-3">
        <span className="text-meta text-ink-soft tabular-nums" aria-live="polite" data-slot="carousel-meta">
          {count === 0 ? "0 / 0" : `${current + 1} / ${count}`}
        </span>
        <button type="button" className={round} aria-label="Thẻ trước" disabled={current <= 0} onClick={() => go(current - 1)}>
          <ArrowLeft aria-hidden="true" className="size-5" />
        </button>
        <button
          type="button"
          className={round}
          aria-label="Thẻ sau"
          disabled={current >= count - 1}
          onClick={() => go(current + 1)}
        >
          <ArrowRight aria-hidden="true" className="size-5" />
        </button>
      </div>
      <div
        ref={track}
        tabIndex={0}
        data-slot="carousel-track"
        onScroll={onScroll}
        onKeyDown={onKeyDown}
        className="flex snap-x snap-mandatory items-start gap-4 overflow-x-auto overscroll-x-contain pb-2 outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus"
      >
        {slides.map((slide, i) => (
          <div
            key={i}
            role="group"
            aria-roledescription="thẻ"
            aria-label={`${i + 1} / ${count}`}
            className="w-[min(380px,86vw)] shrink-0 snap-start"
          >
            {slide}
          </div>
        ))}
      </div>
    </div>
  )
}

export { Carousel }
export type { CarouselProps }
