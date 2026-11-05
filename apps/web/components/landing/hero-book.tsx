"use client";

import type { CSSProperties } from "react";

import { useLamp } from "./landing-root";
import styles from "./landing.module.css";

const at = (i: number) => ({ "--i": i }) as CSSProperties;

/**
 * The Today book of the app, in the hero, with its desk lamp: lit shows the book in the app's
 * light tokens, off in the dark ones, whatever the page's own mode is. Everything but the lamp is
 * decoration, hidden from screen readers behind one description (.sr).
 */
export function HeroBook() {
  const { lit, setLit } = useLamp();
  const tone = lit === null ? undefined : lit ? "light" : "dark";
  return (
    <div className={styles.hbFloat}>
      <div className={styles.hb} id="today-cover" data-tone={tone}>
        <p className={styles.sr}>
          Trang Hôm nay của Essity: phiên ôn 14 câu, khoảng 25 phút. Câu 1 môn Vật lý đại cương, vì sao bầu trời có màu
          xanh, đã được trả lời và chấm Đúng; nguồn là giáo trình Vật lý đại cương trang 112.
        </p>
        <div aria-hidden="true">
          <div className={styles.hbSpine} />
          <div className={styles.hbHead}>
            <span className={styles.cvH}>Hôm nay</span>
          </div>
        </div>
        <button
          className={styles.lamp}
          type="button"
          aria-pressed={lit ?? true}
          aria-controls="today-cover"
          onClick={() => setLit(!(lit ?? true))}
        >
          <span className={styles.lampTrack} aria-hidden="true">
            <i />
          </span>
          <span className={styles.lampLabel}>Đèn bàn</span>
        </button>
        <div aria-hidden="true">
          <div className={styles.stripes}>
            <i />
            <i />
          </div>
          <div className={styles.nv}>
            <b>Phiên ôn</b>
            <em>14 câu</em>
            <em>khoảng 25 phút</em>
          </div>
          <div className={styles.hp}>
            <p className={styles.meta}>
              <span>Vật lý đại cương</span>
            </p>
            <p className={styles.hpQ}>Vì sao bầu trời có màu xanh?</p>
            <p className={styles.ruled}>
              <span style={at(0)}>Ánh sáng xanh bị không khí tán ra</span>{" "}
              <span style={at(1)}>khắp bầu trời nhiều hơn các màu khác.</span>
            </p>
            <svg className={styles.wave} viewBox="0 0 600 14" preserveAspectRatio="none">
              <path
                d="M0 7 Q 15 0 30 7 T 60 7 T 90 7 T 120 7 T 150 7 T 180 7 T 210 7 T 240 7 T 270 7 T 300 7 T 330 7 T 360 7 T 390 7 T 420 7 T 450 7 T 480 7 T 510 7 T 540 7 T 570 7 T 600 7"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              />
            </svg>
            <div className={styles.hpRes}>
              <div className={styles.verdict} style={at(0)}>
                <svg viewBox="0 0 32 32">
                  <circle cx="16" cy="16" r="12" fill="var(--correct)" />
                </svg>
                <strong>Đúng</strong>
              </div>
              <div className={styles.slip} style={at(1)}>
                <div className={styles.slipPic}>
                  <i />
                </div>
                <div>
                  <b>Giáo trình Vật lý</b>
                  <span>trang 112</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
