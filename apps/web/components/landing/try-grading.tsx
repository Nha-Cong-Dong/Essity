"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import { useLamp } from "./landing-root";
import styles from "./landing.module.css";

// "Viết ra, rồi được chấm": three sample answers to one question, graded client-side from fixed
// text. No request leaves the page and no AI is involved (T0.15 card).

type Pick = "du" | "thieu" | "khong";

const PICKS: ReadonlyArray<{ id: Pick; label: string }> = [
  { id: "du", label: "Đủ ý" },
  { id: "thieu", label: "Thiếu một ý" },
  { id: "khong", label: "Không nhớ" },
];

const ANSWER: Record<Pick, string> = {
  du: "Vì Trái Đất tự quay quanh trục. Mặt Trời chỉ chiếu sáng một nửa, nửa đó là ngày, nửa kia là đêm.",
  thieu: "Vì Trái Đất tự quay quanh trục của nó.",
  khong: "Bạn chọn Không nhớ.",
};

const SUN = "Mặt Trời chỉ chiếu sáng một nửa Trái Đất: nửa ấy là ngày, nửa kia là đêm.";
const CITE = "Giáo trình Địa lý đại cương · trang 24";

const k = (i: number) => ({ "--k": i }) as CSSProperties;

function Source({ marked, down }: { marked: "both" | "second"; down?: boolean }) {
  return (
    <div className={styles.r} style={k(3)}>
      <p className={`${styles.tcPen} ${styles.tcH}`}>
        {down ? (
          <svg className={styles.tcDown} viewBox="0 0 12 12" aria-hidden="true">
            <path d="M6 1.5v8M2.5 6.5 6 10l3.5-3.5" />
          </svg>
        ) : null}
        nguồn
      </p>
      <blockquote className={styles.tcSrc}>
        <p>
          {marked === "both" ? (
            <>
              <mark>Trái Đất tự quay quanh trục.</mark> <mark>{SUN}</mark>
            </>
          ) : (
            <>
              Trái Đất tự quay quanh trục. <mark>{SUN}</mark>
            </>
          )}
        </p>
      </blockquote>
      <p className={styles.tcCite}>{CITE}</p>
    </div>
  );
}

const Foot = () => (
  <p className={`${styles.tcFoot} ${styles.r}`} style={k(4)}>
    <span>Chấm sai</span>
  </p>
);

const words = (text: string) =>
  text.split(/\s+/).map((word, i, all) => (
    <span key={i} className={styles.w}>
      {word + (i < all.length - 1 ? " " : "")}
    </span>
  ));

export function TryGrading() {
  const [pick, setPick] = useState<Pick>("thieu");
  const { lit } = useLamp();
  const win = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);

  // The evidence arrow: from "còn thiếu" to the line the app highlighted. Needs real geometry.
  function arrow() {
    const el = win.current;
    const svg = el?.querySelector<SVGSVGElement>(`.${styles.tcArrow}`);
    const rail = el?.querySelector<HTMLElement>(`.${styles.tcRail}`);
    if (!el || !svg || !rail) return;
    const res = rail.querySelector<HTMLElement>(`.${styles.tcRes}:not([hidden])`);
    const miss = res?.querySelector<HTMLElement>(`.${styles.tcMiss}`);
    const mark = res?.querySelector<HTMLElement>("mark");
    if (!miss || !mark || getComputedStyle(svg).display === "none") {
      svg.style.visibility = "hidden";
      return;
    }
    const r = rail.getBoundingClientRect();
    const m = miss.getBoundingClientRect();
    const rect = mark.getClientRects()[0];
    if (!rect) return;
    const y1 = m.top - r.top + 12;
    const y2 = rect.top - r.top + rect.height / 2;
    const h = Math.ceil(y2 + 8);
    svg.style.visibility = "visible";
    svg.setAttribute("height", String(h));
    svg.setAttribute("viewBox", `0 0 28 ${h}`);
    svg
      .querySelector("path")
      ?.setAttribute("d", `M22 ${y1} C 4 ${y1 + 10}, 4 ${y2 - 14}, 22 ${y2} M16 ${y2 - 6} L22 ${y2} L15 ${y2 + 4}`);
  }

  // write → the rule turns hồng → the result rises → the arrow draws → the highlight sweeps (~1.9 s).
  function play() {
    const el = win.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    arrow();
    const steps = [styles.b2, styles.b3, styles.b4, styles.b5];
    if (reduce) {
      el.classList.remove(styles.pre, ...steps);
      return;
    }
    el.classList.remove(...steps);
    el.classList.add(styles.pre);
    const shown = Array.from(el.querySelectorAll<HTMLElement>(`.${styles.tcAns}:not([hidden]) .${styles.w}`));
    shown.forEach((w) => w.classList.remove(styles.on));
    const caret = el.querySelector<HTMLElement>(`.${styles.tcAns}:not([hidden]) .${styles.tcCaret}`);
    if (caret) {
      caret.style.animation = "none";
      void caret.offsetWidth;
      caret.style.animation = "";
    }
    shown.forEach((w, i) => timers.current.push(window.setTimeout(() => w.classList.add(styles.on), 60 + i * 45)));
    const t = 60 + shown.length * 45 + 80;
    [t, t + 320, t + 720, t + 1120].forEach((at, i) =>
      timers.current.push(window.setTimeout(() => el.classList.add(steps[i]), at)),
    );
  }

  // The first play waits until the window is in view; every later one follows a pick.
  useEffect(() => {
    const el = win.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const onResize = () => arrow();
    window.addEventListener("resize", onResize, { passive: true });
    void document.fonts?.ready.then(arrow);
    let io: IntersectionObserver | null = null;
    if (reduce || !("IntersectionObserver" in window)) {
      play();
    } else {
      el.classList.add(styles.pre);
      io = new IntersectionObserver(
        (entries) => {
          if (!entries[0]?.isIntersecting) return;
          io?.disconnect();
          play();
        },
        { rootMargin: "0px 0px -20% 0px" },
      );
      io.observe(el);
    }
    return () => {
      window.removeEventListener("resize", onResize);
      io?.disconnect();
      timers.current.forEach(window.clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    play();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick]);

  return (
    <div className={styles.tcStage} data-reveal style={{ "--d": "120ms" } as CSSProperties}>
      <div
        ref={win}
        id="ts"
        data-sheet
        className={styles.tcWin}
        data-tone={lit === null ? undefined : lit ? "light" : "dark"}
      >
        <div className={styles.tcBar} aria-hidden="true">
          <span className={styles.n}>Câu 3 / 14</span>
          <span className={styles.tcProg}>
            <i />
          </span>
        </div>
        <div className={styles.tcBody}>
          <span className={styles.tcRule} aria-hidden="true" />
          <span className={styles.tcHinge} aria-hidden="true">
            <svg viewBox="0 0 14 14">
              <path d="M5 3l4 4-4 4" />
            </svg>
          </span>
          <div className={styles.tcAsk}>
            <p className={styles.tcMeta}>Địa lý đại cương</p>
            <p className={styles.tcQ}>Vì sao có ngày và đêm?</p>
            <p className={`${styles.tcPen} ${styles.tcPickL}`} id="tc-pick-l">
              chọn một câu trả lời mẫu, xem app chấm
            </p>
            <div className={styles.tcPicks} role="group" aria-labelledby="tc-pick-l">
              {PICKS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  className={styles.tcPick}
                  aria-pressed={pick === id}
                  onClick={() => setPick(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            {PICKS.map(({ id }) => (
              <p key={id} className={id === "khong" ? `${styles.tcAns} ${styles.ro}` : styles.tcAns} hidden={pick !== id}>
                {words(ANSWER[id])}
                <span className={styles.tcCaret} aria-hidden="true" />
              </p>
            ))}
          </div>
          <div className={styles.tcRail} aria-live="polite">
            <svg className={styles.tcArrow} aria-hidden="true" focusable="false">
              <path pathLength={1} d="" />
            </svg>

            <div className={styles.tcRes} hidden={pick !== "du"}>
              <p className={styles.r} style={k(0)}>
                <span className={styles.tcChip}>
                  <svg viewBox="0 0 12 12" aria-hidden="true">
                    <circle cx="6" cy="6" r="5.5" fill="var(--correct)" />
                  </svg>
                  Đúng
                </span>
              </p>
              <p className={`${styles.tcPen} ${styles.tcLevel} ${styles.r}`} style={k(1)}>
                đủ cả hai ý
              </p>
              <Source marked="both" />
              <Foot />
            </div>

            <div className={styles.tcRes} hidden={pick !== "thieu"}>
              <p className={styles.r} style={k(0)}>
                <span className={styles.tcChip}>
                  <svg viewBox="0 0 12 12" aria-hidden="true">
                    <circle cx="6" cy="6" r="5" fill="none" stroke="var(--partial)" strokeWidth="1.5" />
                    <path d="M6 1 A5 5 0 0 0 6 11 Z" fill="var(--partial)" />
                  </svg>
                  Đúng một phần
                </span>
              </p>
              <p className={`${styles.tcPen} ${styles.tcLevel} ${styles.r}`} style={k(1)}>
                nhớ được một ý
              </p>
              <div className={styles.r} style={k(2)}>
                <p className={`${styles.tcPen} ${styles.tcH}`}>còn thiếu</p>
                <p className={styles.tcMiss}>
                  <span>Mặt Trời chỉ chiếu sáng một nửa Trái Đất.</span>
                </p>
              </div>
              <Source marked="second" down />
              <Foot />
            </div>

            <div className={styles.tcRes} hidden={pick !== "khong"}>
              <p className={styles.r} style={k(0)}>
                <span className={styles.tcChip}>
                  <svg viewBox="0 0 12 12" aria-hidden="true">
                    <circle cx="6" cy="6" r="5" fill="none" stroke="var(--pencil)" strokeWidth="1.5" />
                  </svg>
                  Không nhớ
                </span>
              </p>
              <p className={`${styles.tcPen} ${styles.tcLevel} ${styles.r}`} style={k(1)}>
                đáp án ở trang nguồn
              </p>
              <Source marked="both" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
