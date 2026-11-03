import type { CSSProperties, ReactNode } from "react";

import { HeroBook } from "./hero-book";
import { LandingRoot } from "./landing-root";
import styles from "./landing.module.css";
import { TryGrading } from "./try-grading";

// The public landing at "/" (T0.15), from docs/design/landing.html (approved, round 10). The H1 and
// the line under it are the user's words, verbatim (landing.md). Nothing here promises a thing the
// app does not do; no figures, quotes, prices or other platforms.

const vars = (v: Record<string, string | number>) => v as CSSProperties;

// Added to <html> before first paint, so nothing hides without JS and nothing flashes.
const JS_FLAG = "document.documentElement.classList.add('js')";

const STAR = "M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z";
const ARROW = (
  <>
    <path pathLength={1} d="M6 52 C 34 10, 96 2, 146 30" />
    <path pathLength={1} d="M130 14 L147 31 L126 40" />
  </>
);

function Motif({
  kind,
  className,
  viewBox,
  children,
}: {
  kind: "doodle" | "sticker" | "dots";
  className: string;
  viewBox: string;
  children: ReactNode;
}) {
  return (
    <svg className={`${styles.motif} ${styles[kind]} ${className}`} viewBox={viewBox} aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

const Sticker = ({ className }: { className: string }) => (
  <Motif kind="sticker" className={className} viewBox="0 0 100 100">
    <path d={STAR} />
  </Motif>
);

const Dots = ({ className, id }: { className: string; id: string }) => (
  <Motif kind="dots" className={className} viewBox="0 0 240 160">
    <defs>
      <pattern id={id} width="16" height="16" patternUnits="userSpaceOnUse">
        <circle cx="2" cy="2" r="1.6" />
      </pattern>
    </defs>
    <rect width="240" height="160" fill={`url(#${id})`} />
  </Motif>
);

const QA: ReadonlyArray<{ q: string; mark: ReactNode; a: ReactNode }> = [
  {
    q: "Cần chuẩn bị gì?",
    mark: <path pathLength={1} d="M20 3 L23 16 L36 20 L23 24 L20 37 L17 24 L4 20 L17 16 Z" />,
    a: (
      <>
        <span className={styles.key}>Tên môn, ngày thi và giáo trình chính</span>, vì có giáo trình app mới lập được mục
        lục. Đề thi mẫu và ảnh vở thêm lúc nào cũng được.
      </>
    ),
  },
  {
    q: "AI chấm sai thì sao?",
    mark: (
      <>
        <path
          pathLength={1}
          d="M20 4 C 30 4, 37 11, 37 20 C 37 30, 29 37, 20 37 C 10 37, 3 29, 4 19 C 5 10, 12 5, 22 5"
        />
        <path pathLength={1} d="M12 21 L18 27 L29 14" />
      </>
    ),
    a: (
      <>
        Mỗi lời chấm <span className={styles.key}>kèm trang nguồn</span> để bạn đối chiếu. Thấy chưa đúng thì bấm Chấm sai,
        lịch ôn của câu đó tính lại ngay.
      </>
    ),
  },
  {
    q: "Lịch ôn dựa trên gì?",
    mark: (
      <>
        <path pathLength={1} d="M33 15 C 29 7, 19 4, 11 9 C 3 15, 4 28, 13 33 C 22 38, 32 33, 35 25" />
        <path pathLength={1} d="M27 14 L34 16 L35 8" />
      </>
    ),
    a: (
      <>
        Trên FSRS, một thuật toán lặp lại ngắt quãng đã được công bố, và trên{" "}
        <span className={styles.key}>kết quả chấm thật</span> của bạn. Không câu nào xếp sau ngày thi.
      </>
    ),
  },
  {
    q: "Nghỉ vài hôm thì sao?",
    mark: (
      <>
        <path pathLength={1} d="M27 5 C 15 6, 7 15, 8 25 C 9 33, 17 38, 26 36 C 18 32, 15 24, 17 16 C 19 10, 23 7, 27 5 Z" />
        <path pathLength={1} d="M31 22 h6 l-6 7 h6" />
      </>
    ),
    a: (
      <>
        Mở lại là app <span className={styles.key}>gợi ý đúng chỗ bạn dừng</span>.
      </>
    ),
  },
  {
    q: "Sửa nhanh thế nào?",
    mark: (
      <>
        <path pathLength={1} d="M8 32 L10 24 L28 6 L34 12 L16 30 Z" />
        <path pathLength={1} d="M24 10 L30 16" />
      </>
    ),
    a: (
      <>
        Gõ một dòng vào ô lệnh ở đầu trang, ví dụ “mục 3.3 tôi học rồi”. App cho thấy{" "}
        <span className={styles.key}>đúng thay đổi</span>, kèm nút Hoàn tác.
      </>
    ),
  },
];

const TOC: ReadonlyArray<readonly [string, string, string, string?]> = [
  ["3.1", "Địa chỉ IP", "✓ Đã học", "nxR1"],
  ["3.2", "Chia mạng con", "✓ Đã học"],
  ["3.3", "Định tuyến", "→ Tiếp theo", "nxNext"],
  ["3.4", "Chuyển mạch", ""],
];

const KINDS: ReadonlyArray<readonly [string, string, string?]> = [
  ["Tính toán", "Chia mạng 192.168.1.0/24 thành 4 mạng con.", "→ Gợi ý: liên quan tới Định tuyến"],
  ["Giải thích", "Vì sao TCP dùng bắt tay ba bước?"],
  ["So sánh", "So sánh TCP và UDP."],
];

const STEPS: ReadonlyArray<{ grow: string; delay?: string; seg: string; segSub: string; h: string; p: string }> = [
  {
    grow: "1.3",
    seg: "Bài học",
    segSub: "ảnh vở hoặc vài dòng",
    h: "Nộp bài học",
    p: "Gửi ảnh vở hoặc vài dòng. App tóm thành ý chính, bạn xem và bấm lưu.",
  },
  {
    grow: "2",
    delay: "90ms",
    seg: "App làm",
    segSub: "trong lúc bạn nghỉ",
    h: "App soạn câu hỏi",
    p: "Câu hỏi bám vào các ý bạn đã lưu, gắn với đúng trang giáo trình.",
  },
  {
    grow: "3.2",
    delay: "180ms",
    seg: "Mỗi tối",
    segSub: "khoảng 25 phút",
    h: "Mỗi tối mở ra là ôn",
    p: "Phiên hôm nay đã soạn sẵn, câu sắp quên được hỏi trước.",
  },
];

export function Landing() {
  return (
    <LandingRoot>
      <script dangerouslySetInnerHTML={{ __html: JS_FLAG }} />

      <header className={`${styles.hero} ${styles.wrap}`} id="dau-trang" data-hero>
        <nav className={styles.bar} aria-label="Chính">
          <a className={styles.mark} href="#dau-trang">
            Essity
          </a>
          <a className={styles.login} href="/login">
            Đăng nhập
          </a>
        </nav>
        <div className={styles.heroDots} aria-hidden="true" />
        <div className={styles.heroDisc} aria-hidden="true" />
        <div className={styles.heroMain}>
          <div className={styles.heroText}>
            <h1 className={styles.lines}>
              <span className={styles.line}>
                <span data-line style={vars({ "--i": 0 })}>
                  Tối nay ôn gì,
                </span>
              </span>{" "}
              <span className={styles.line}>
                <span data-line style={vars({ "--i": 1 })}>
                  đã có app lo
                </span>
              </span>
            </h1>
            <p className={styles.lead} data-load style={vars({ "--d": "420ms" })}>
              Trợ lí học tập thông minh. Quản lí lịch ôn tập hiệu quả với thuật toán FSRS.
            </p>
            <div className={styles.buy} data-load style={vars({ "--d": "540ms" })}>
              <a className={styles.btn} href="/register">
                Đăng ký
              </a>
            </div>
          </div>
          <div className={styles.heroPic}>
            <HeroBook />
            <div className={styles.hbShadow} aria-hidden="true" />
          </div>
        </div>
        <Motif kind="doodle" className={styles.mHeroStar} viewBox="0 0 62 62">
          <path
            pathLength={1}
            d="M31 4 L38.5 23 L58 24.5 L42.5 37 L48 56.5 L31 45.5 L13.5 57 L19.5 37.5 L3.5 25.5 L23.5 23.5 Z"
          />
        </Motif>
        <Motif kind="doodle" className={styles.mHeroArrow} viewBox="0 0 152 60">
          {ARROW}
        </Motif>
        <Sticker className={styles.mHeroSticker} />
      </header>

      <main>
        <section className={`${styles.tc} ${styles.wrap}`} id="thu-cham" aria-labelledby="h-try" data-once>
          <div className={styles.tcHead}>
            <h2 id="h-try" data-reveal>
              Viết ra, rồi được chấm
            </h2>
          </div>
          <TryGrading />
        </section>

        <section className={`${styles.steps} ${styles.wrap}`} id="cach-hoat-dong" aria-labelledby="h-steps" data-once>
          <Dots className={styles.mStepsDots} id="dots-a" />
          <Motif kind="doodle" className={styles.mStepsArrow} viewBox="0 0 152 60">
            {ARROW}
          </Motif>
          <h2 id="h-steps" data-reveal>
            Từ buổi học tới phiên ôn
          </h2>
          <ol className={styles.stepList}>
            {STEPS.map((s) => (
              <li
                key={s.h}
                className={styles.step}
                style={vars({ "--grow": s.grow, ...(s.delay ? { "--d": s.delay } : {}) })}
                data-reveal
              >
                <div className={styles.seg} aria-hidden="true">
                  <b>{s.seg}</b>
                  <span>{s.segSub}</span>
                </div>
                <h3>{s.h}</h3>
                <p>{s.p}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={`${styles.nx} ${styles.wrap}`} id="hoc-gi-tiep" aria-labelledby="h-nx-a" data-once>
          <div className={`${styles.grid}`}>
            <div className={styles.nxText}>
              <h2 id="h-nx-a" data-reveal>
                Học gì tiếp, đã có gợi ý
              </h2>
              <p data-reveal style={vars({ "--d": "90ms" })}>
                Tải giáo trình chính lên, app lập mục lục môn học. Mỗi lần mở, app gợi ý mục nên học tiếp và nói rõ vì sao.
              </p>
            </div>
            <div className={styles.nxPic} data-reveal style={vars({ "--d": "140ms" })}>
              <p className={styles.sr}>
                Mục lục môn Mạng máy tính: mục 3.1 và 3.2 đã học, mục 3.3 được gợi ý học tiếp, mục 3.4 chưa học. Gợi ý, bạn
                chọn.
              </p>
              <div className={styles.nxCard} aria-hidden="true">
                <div className={styles.nxCardH}>
                  <b>Mạng máy tính</b>
                  <span className={styles.nxTag}>Gợi ý, bạn chọn</span>
                </div>
                <ul className={styles.nxToc}>
                  {TOC.map(([n, t, st, cls]) => (
                    <li key={n} className={cls ? styles[cls] : undefined}>
                      <span className={styles.nxN}>{n}</span>
                      <span>{t}</span>
                      <span className={styles.nxS}>{st}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className={`${styles.nx} ${styles.nxB} ${styles.wrap}`} id="luyen-dang-de" aria-labelledby="h-nx-b" data-once>
          <div className={`${styles.grid}`}>
            <div className={styles.nxText}>
              <h2 id="h-nx-b" data-reveal>
                Luyện đúng dạng đề
              </h2>
              <p data-reveal style={vars({ "--d": "90ms" })}>
                Tải đề thi mẫu, app tách từng câu, gom theo dạng và gợi ý câu nên luyện trước dựa trên bản đồ kiến thức của bạn. Mỗi câu chấm theo từng ý và chỉ ra nguồn.
              </p>
            </div>
            <div className={styles.nxPic} data-reveal style={vars({ "--d": "140ms" })}>
              <p className={styles.sr}>Ba dạng câu; câu tính toán đứng đầu, được gợi ý luyện trước vì liên quan tới mục Định tuyến</p>
              <div className={styles.nxCard} aria-hidden="true">
                <ul className={styles.nxKinds}>
                  {KINDS.map(([chip, q, why]) => (
                    <li key={chip} className={why ? styles.nxPick : undefined}>
                      <span className={styles.nxChip}>{chip}</span>
                      <span className={styles.nxQ}>
                        {q}
                        {why ? <span className={styles.nxWhy}>{why}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className={`${styles.faq} ${styles.wrap}`} id="hoi-dap" aria-labelledby="h-faq" data-once>
          <Motif kind="doodle" className={styles.mFaqQ} viewBox="0 0 76 88">
            <path pathLength={1} d="M18 30 C 16 10, 56 4, 58 26 C 60 44, 38 44, 38 64" />
            <path pathLength={1} d="M36 80 a 3 3 0 1 0 6 0 a 3 3 0 1 0 -6 0" />
          </Motif>
          <Sticker className={styles.mFaqSticker} />
          <h2 id="h-faq" data-reveal>
            Hỏi đáp
          </h2>
          <dl className={styles.qa}>
            {QA.map(({ q, mark, a }, i) => (
              <div key={q} className={styles.qaItem} style={vars({ "--k": i })}>
                <svg
                  className={`${styles.doodle} ${styles.qaRule}`}
                  viewBox="0 0 1000 12"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                  focusable="false"
                >
                  <path pathLength={1} d="M2 7 C 120 3, 260 10, 420 6 S 720 3, 860 8 S 960 6, 998 5" />
                </svg>
                <dt data-reveal>
                  <svg
                    className={`${styles.doodle} ${styles.qaMark}`}
                    viewBox="0 0 40 40"
                    aria-hidden="true"
                    focusable="false"
                  >
                    {mark}
                  </svg>
                  <span>{q}</span>
                </dt>
                <dd data-reveal style={vars({ "--d": "80ms" })}>
                  {a}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </main>

      <footer className={styles.end} aria-labelledby="h-end" data-once data-end>
        <Sticker className={styles.mEndBurst} />
        <Motif kind="doodle" className={styles.mEndSpark} viewBox="0 0 40 40">
          <path pathLength={1} d="M20 2 V 14 M20 26 V 38 M2 20 H 14 M26 20 H 38" />
        </Motif>
        <Dots className={styles.mEndDots} id="dots-b" />
        <div className={`${styles.grid} ${styles.endMain}`}>
          <h2 id="h-end" data-reveal>
            Tối nay mở vở ra, việc đầu tiên đã nằm sẵn
          </h2>
          <div className={styles.endAct} data-reveal style={vars({ "--d": "100ms" })}>
            <a className={styles.btn} href="/register">
              Đăng ký
            </a>
            <p className={styles.alt}>
              Đã có tài khoản? <a href="/login">Đăng nhập</a>
            </p>
          </div>
        </div>
        <div className={styles.legal}>
          <span>© 2026 Essity</span>
          <span>Dùng trên trình duyệt máy tính, sáng hoặc tối theo máy của bạn.</span>
        </div>
        <div className={styles.wordmarkMask}>
          <p className={styles.wordmark} aria-hidden="true">
            Essity
          </p>
        </div>
      </footer>
    </LandingRoot>
  );
}
