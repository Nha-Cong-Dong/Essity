"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import styles from "./landing.module.css";

// The page's one piece of shared state: the desk lamp on the hero's Today book. Lit = the book
// (and the grading window under it) in the app's light tokens, off = the dark ones. `null` means
// "follow the page", which is how a visitor starts (lamp on a light page, off on a dark one).
type Lamp = { lit: boolean | null; setLit: (lit: boolean) => void };
const LampContext = createContext<Lamp>({ lit: null, setLit: () => undefined });
export const useLamp = () => useContext(LampContext);

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * The landing's wrapper: marks <html> as scripted (so nothing hides without JS), and runs the
 * once-only scroll effects of the approved mockup (reveals, section "seen" flags, the book that
 * straightens, Essity rising at the very bottom, the grading sheet leaning to the pointer).
 * Under prefers-reduced-motion every piece shows its finished state at once.
 */
export function LandingRoot({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const [lit, setLit] = useState<boolean | null>(null);
  const lamp = useMemo(() => ({ lit, setLit }), [lit]);

  useEffect(() => {
    const host = root.current;
    if (!host) return;
    const html = document.documentElement;
    html.classList.add("js");
    const reduce = reducedMotion();
    const cleanups: Array<() => void> = [() => html.classList.remove("js")];
    const all = (selector: string) => Array.from(host.querySelectorAll<HTMLElement>(selector));
    const hasObserver = "IntersectionObserver" in window;

    // Reveal once, when an element's top reaches ~88% of the viewport.
    const reveals = all("[data-reveal]");
    if (!hasObserver || reduce) {
      reveals.forEach((el) => el.classList.add(styles.isIn));
    } else {
      const io = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (!e.isIntersecting) continue;
            e.target.classList.add(styles.isIn);
            io.unobserve(e.target);
          }
        },
        { rootMargin: "0px 0px -12% 0px", threshold: 0 },
      );
      reveals.forEach((el) => io.observe(el));
      // A jump can carry a short element past the viewport between two frames: sweep what is above the fold.
      let queued = false;
      const sweep = () => {
        queued = false;
        for (const el of reveals) {
          if (!el.classList.contains(styles.isIn) && el.getBoundingClientRect().top < window.innerHeight * 0.88) {
            el.classList.add(styles.isIn);
            io.unobserve(el);
          }
        }
      };
      const onScroll = () => {
        if (!queued) {
          queued = true;
          requestAnimationFrame(sweep);
        }
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      cleanups.push(() => {
        io.disconnect();
        window.removeEventListener("scroll", onScroll);
      });
    }

    // Once-only effects: a section that comes into view gets .isSeen and is let go.
    const once = all("[data-once]");
    if (!hasObserver || reduce) {
      once.forEach((el) => el.classList.add(styles.isSeen));
    } else {
      const io = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (!e.isIntersecting) continue;
            e.target.classList.add(styles.isSeen);
            io.unobserve(e.target);
          }
        },
        { rootMargin: "0px 0px -18% 0px", threshold: 0 },
      );
      once.forEach((el) => io.observe(el));
      cleanups.push(() => io.disconnect());
    }

    // Essity waits for the bottom of the page, not for the footer to come into view.
    const end = host.querySelector<HTMLElement>("[data-end]");
    if (end) {
      if (reduce) {
        end.classList.add(styles.wmIn);
      } else {
        const atBottom = () => {
          if (window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 2) return;
          end.classList.add(styles.wmIn);
          window.removeEventListener("scroll", atBottom);
          window.removeEventListener("resize", atBottom);
        };
        window.addEventListener("scroll", atBottom, { passive: true });
        window.addEventListener("resize", atBottom);
        atBottom();
        cleanups.push(() => {
          window.removeEventListener("scroll", atBottom);
          window.removeEventListener("resize", atBottom);
        });
      }
    }

    // The Today book straightens once, the first time the page is scrolled.
    const hero = host.querySelector<HTMLElement>("[data-hero]");
    if (hero) {
      const settle = () => {
        if (window.scrollY > 60) {
          hero.classList.add(styles.settled);
          window.removeEventListener("scroll", settle);
        }
      };
      window.addEventListener("scroll", settle, { passive: true });
      cleanups.push(() => window.removeEventListener("scroll", settle));
    }

    // A light lean toward the pointer: the grading sheet tilts. Fine pointers only, one frame at a time.
    const sheet = host.querySelector<HTMLElement>("[data-sheet]");
    if (sheet && !reduce && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      sheet.classList.add(styles.lean);
      let raf = 0;
      let last: PointerEvent | null = null;
      const frame = () => {
        raf = 0;
        if (!last) return;
        const r = sheet.getBoundingClientRect();
        if (r.bottom > 0 && r.top < window.innerHeight) {
          const x = (last.clientX - r.left) / r.width - 0.5;
          const y = (last.clientY - r.top) / r.height - 0.5;
          sheet.style.setProperty("--ry", `${(x * 3).toFixed(2)}deg`);
          sheet.style.setProperty("--rx", `${(-y * 2.4).toFixed(2)}deg`);
        }
      };
      const onMove = (e: PointerEvent) => {
        last = e;
        if (!raf) raf = requestAnimationFrame(frame);
      };
      const onLeave = () => {
        sheet.style.setProperty("--rx", "0deg");
        sheet.style.setProperty("--ry", "0deg");
      };
      window.addEventListener("pointermove", onMove, { passive: true });
      sheet.addEventListener("pointerleave", onLeave);
      cleanups.push(() => {
        window.removeEventListener("pointermove", onMove);
        sheet.removeEventListener("pointerleave", onLeave);
        if (raf) cancelAnimationFrame(raf);
      });
    }

    return () => cleanups.forEach((fn) => fn());
  }, []);

  return (
    <LampContext.Provider value={lamp}>
      <div ref={root} className={styles.lp}>
        {children}
      </div>
    </LampContext.Provider>
  );
}
