"use client";

import { useLamp } from "./landing-root";
import styles from "./landing.module.css";


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
          Trang Hôm nay của Essity có ba phần: Học gì tiếp là mục 3.3 Định tuyến vì mục 3.2 đã học; Ôn hôm nay có 8 thẻ đến
          hạn, khoảng 15 phút; Luyện tập có 5 câu sẵn sàng, câu tính toán đứng đầu.
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
          <div className={`${styles.nv} ${styles.hbRow}`}>
            <b>Học gì tiếp</b>
            <em>3.3 Định tuyến</em>
            <em>vì mục 3.2 đã học</em>
          </div>
          <div className={`${styles.nv} ${styles.hbRow}`}>
            <b>Ôn hôm nay</b>
            <em>8 thẻ đến hạn</em>
            <em>khoảng 15 phút</em>
          </div>
          <div className={`${styles.nv} ${styles.hbRow}`}>
            <b>Luyện tập</b>
            <em>5 câu sẵn sàng</em>
            <em>câu tính toán đứng đầu</em>
          </div>
        </div>
      </div>
    </div>
  );
}
