import type { CSSProperties, ReactNode } from "react";

import { NxKind, NxList, NxRow } from "@/components/ui/nx-list";

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
function Motif({
  kind,
  className,
  viewBox,
  children,
}: {
  kind: "sticker";
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

const QA: ReadonlyArray<{ q: string; a: ReactNode }> = [
  {
    q: "Cần chuẩn bị gì?",
    a: (
      <>
        <span className={styles.key}>Tên môn, ngày thi và giáo trình chính</span>, vì có giáo trình app mới lập được mục
        lục. Đề thi mẫu và ảnh vở thêm lúc nào cũng được.
      </>
    ),
  },
  {
    q: "AI chấm sai thì sao?",
    a: (
      <>
        Mỗi lời chấm <span className={styles.key}>kèm trang nguồn</span> để bạn đối chiếu. Thấy chưa đúng thì bấm Chấm sai,
        lịch ôn của câu đó tính lại ngay.
      </>
    ),
  },
  {
    q: "Lịch ôn dựa trên gì?",
    a: (
      <>
        Trên FSRS, một thuật toán lặp lại ngắt quãng đã được công bố, và trên{" "}
        <span className={styles.key}>kết quả chấm thật</span> của bạn. Không câu nào xếp sau ngày thi.
      </>
    ),
  },
  {
    q: "Nghỉ vài hôm thì sao?",
    a: (
      <>
        Mở lại là app <span className={styles.key}>gợi ý đúng chỗ bạn dừng</span>.
      </>
    ),
  },
  {
    q: "Sửa nhanh thế nào?",
    a: (
      <>
        Gõ một dòng vào ô lệnh ở đầu trang, ví dụ “mục 3.3 tôi học rồi”. App cho thấy{" "}
        <span className={styles.key}>đúng thay đổi</span>, kèm nút Hoàn tác.
      </>
    ),
  },
];

const DONE = (
  <span className="inline-flex items-center gap-1.5">
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8.5 L6.5 12 L13 4.5" />
    </svg>
    Đã học
  </span>
);

const TOC: ReadonlyArray<readonly [string, string, ReactNode, string?]> = [
  ["3.1", "Địa chỉ IP", DONE, "nxR1"],
  ["3.2", "Chia mạng con", DONE],
  ["3.3", "Định tuyến", "Tiếp theo", "nxNext"],
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
          </div>
        </div>
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
              <div aria-hidden="true">
                <NxList title="Mạng máy tính" hint="Gợi ý, bạn chọn" titleAs="b">
                  {TOC.map(([n, t, st, cls]) => (
                    <NxRow
                      key={n}
                      lead={n}
                      state={st}
                      next={cls === "nxNext"}
                      className={cls === "nxR1" ? "max-[700px]:hidden" : "max-[700px]:min-h-10 max-[700px]:gap-2.5 max-[700px]:px-3"}
                    >
                      {t}
                    </NxRow>
                  ))}
                </NxList>
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
              <div aria-hidden="true">
                <NxList>
                  {KINDS.map(([chip, q, why]) => (
                    <NxKind key={chip} chip={chip} why={why} pick={Boolean(why)}>
                      {q}
                    </NxKind>
                  ))}
                </NxList>
              </div>
            </div>
          </div>
        </section>

        <section className={`${styles.faq} ${styles.wrap}`} id="hoi-dap" aria-labelledby="h-faq" data-once>
          <h2 id="h-faq" data-reveal>
            Hỏi đáp
          </h2>
          <dl className={styles.qa}>
            {QA.map(({ q, a }, i) => (
              <div key={q} className={styles.qaItem} style={vars({ "--k": i })}>
                <dt data-reveal>
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
