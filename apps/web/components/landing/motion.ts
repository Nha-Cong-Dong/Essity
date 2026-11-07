// LANDING-V61-PORT: the motion layer of landing v6.1, ported from the approved mockup (versions/v6.1/landing-v6.js).
// The markup is finished and readable without it (landing.tsx); this only animates it:
// - nothing moves until the visitor has really scrolled; the default state is the finished one;
// - prefers-reduced-motion: every demo shows its finished state, nothing repeats;
// - the pause button (WCAG 2.2.2) stops every repeating motion and is remembered;
// - startLanding returns a cleanup that stops timers, observers and listeners and puts touched nodes back, so it is safe
//   under React strict mode (effect runs twice in dev).
import { fsrsCurve } from "./fsrs-curve";
import { graphLayout, graphModel } from "./graph-data";

const TROUGH = fsrsCurve().trough;
const SVGNS = "http://www.w3.org/2000/svg";
export const PAUSE_KEY = "essity-motion-paused";

type El = HTMLElement;
type Svg = SVGElement;
type Ready = () => boolean;

const MD_LINES = [
  "## Công thức Einstein",
  "- Năng lượng nằm sẵn trong khối lượng.",
  "- **Một hạt gạo** chứa năng lượng cỡ cả một thành phố.",
  "$$E = mc^2$$",
  "$$S = \\pi r^2$$",
  "> Nguồn: tr. 3",
];
const DIFF_TEXT = "Mục 2.1 · Hiệu ứng Mpemba: <s>Chưa học</s> → <strong>Đã học</strong>";

export function startLanding(root: El): () => void {
  const html = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canObserve = typeof IntersectionObserver !== "undefined" && typeof ResizeObserver !== "undefined";
  let alive = true;
  const undo: Array<() => void> = [];
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const $ = (s: string, r: ParentNode = root) => [...r.querySelectorAll<El>(s)];
  const $1 = (s: string, r: ParentNode = root) => r.querySelector<El>(s);
  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      if (!alive) return; // after cleanup an async script simply never resumes
      const id = setTimeout(() => {
        timers.delete(id);
        resolve();
      }, ms);
      timers.add(id);
    });
  const mk = (tag: string, attrs: Record<string, string | number> = {}, parent?: Element) => {
    const e = document.createElementNS(SVGNS, tag);
    for (const k in attrs) e.setAttribute(k, String(attrs[k]));
    if (parent) parent.appendChild(e);
    return e as Svg;
  };
  const listen = <T extends EventTarget>(t: T, type: string, fn: (e: never) => void, opts?: AddEventListenerOptions) => {
    t.addEventListener(type, fn as EventListener, opts);
    undo.push(() => t.removeEventListener(type, fn as EventListener, opts));
  };
  const watchIO = (cb: IntersectionObserverCallback, opts?: IntersectionObserverInit) => {
    const io = new IntersectionObserver(cb, opts);
    undo.push(() => io.disconnect());
    return io;
  };
  const watchRO = (cb: () => void) => {
    const ro = new ResizeObserver(cb);
    undo.push(() => ro.disconnect());
    return ro;
  };
  /** Put a leaf node's children back exactly as the server rendered them when the effect is cleaned up. */
  const snap = (el: Element | null) => {
    if (!el) return;
    const saved = el.innerHTML;
    undo.push(() => {
      el.innerHTML = saved;
    });
  };
  const addClass = (el: Element, cls: string) => {
    el.classList.add(cls);
  };

  html.classList.add("js");
  undo.push(() => html.classList.remove("js"));

  /* ---------- pause ---------- */
  let paused = false;
  try {
    paused = localStorage.getItem(PAUSE_KEY) === "1";
  } catch {
    /* storage may be blocked: the default is "not paused" */
  }
  const btn = $1("[data-pause]") as HTMLButtonElement | null;
  const applyPause = () => {
    html.classList.toggle("paused", paused);
    if (btn) {
      const l = paused ? "Bật lại chuyển động" : "Tạm dừng chuyển động";
      btn.setAttribute("aria-pressed", String(paused));
      btn.setAttribute("aria-label", l);
      btn.title = l;
    }
  };
  applyPause();
  undo.push(() => {
    html.classList.remove("paused");
    btn?.setAttribute("aria-pressed", "false");
    btn?.setAttribute("aria-label", "Tạm dừng chuyển động");
    if (btn) btn.title = "Tạm dừng chuyển động";
  });
  if (btn) {
    listen(btn, "click", () => {
      paused = !paused;
      try {
        localStorage.setItem(PAUSE_KEY, paused ? "1" : "0");
      } catch {
        /* ignore */
      }
      applyPause();
    });
  }
  const running = () => alive && !paused && !document.hidden && !reduce;

  /* ---------- KaTeX (loaded on demand; the plain text "E = mc²" is already there) ---------- */
  const texEls = $("[data-tex]");
  texEls.forEach(snap);
  void import("katex")
    .then((m) => {
      if (!alive) return;
      const katex = m.default;
      texEls.forEach((e) => {
        try {
          katex.render(e.dataset.tex ?? "", e, { throwOnError: false });
        } catch {
          /* keep the plain text */
        }
      });
    })
    .catch(() => {});

  const feats = $("[data-feat]");
  const hero = $1("[data-hero]");
  const end = $1("[data-end]");
  undo.push(() => {
    feats.forEach((f) => f.classList.remove("in", "off"));
    hero?.classList.remove("off");
    end?.classList.remove("wm-in");
    hero?.style.removeProperty("--sy");
    hero?.style.removeProperty("--rot");
  });

  /* no IntersectionObserver (very old browser, tests): the finished state, nothing animates */
  if (!canObserve) {
    feats.forEach((f) => addClass(f, "in"));
    end?.classList.add("wm-in");
    return () => undo.splice(0).reverse().forEach((f) => f());
  }

  /* ---------- nothing animates until the visitor has really scrolled ---------- */
  let scrolled = scrollY > 40;
  const waiting = new Set<() => void>();
  listen(
    window,
    "scroll",
    () => {
      if (!scrolled && scrollY > 40) {
        scrolled = true;
        waiting.forEach((fn) => fn());
        waiting.clear();
      }
    },
    { passive: true },
  );
  const whenScrolled = (fn: () => void) => (scrolled ? fn() : waiting.add(fn));

  /* ---------- reveal on view ---------- */
  if (reduce) feats.forEach((f) => addClass(f, "in"));
  else {
    const io = watchIO(
      (es) =>
        es.forEach((e) => {
          if (!e.isIntersecting) return;
          const t = e.target;
          io.unobserve(t);
          whenScrolled(() => addClass(t, "in"));
        }),
      { rootMargin: "0px 0px 15% 0px" },
    );
    feats.forEach((f) => io.observe(f));
  }

  /* the try-it block and the FAQ have no "in" state; the doodle FSRS hand sits on the curve */
  const demoFsrs = $1(".fsrs-demo");
  const curve = demoFsrs ? $1(".curve", demoFsrs) : null;
  const fhand = $1("[data-fsrs-hand]");
  if (demoFsrs && curve && fhand) {
    const place = () => {
      const d = demoFsrs.getBoundingClientRect();
      const c = curve.getBoundingClientRect();
      fhand.style.left = c.left - d.left + (TROUGH.x / 900) * c.width + 30 + "px";
      fhand.style.top = c.top - d.top + (TROUGH.y / 300) * c.height - 14 + "px";
      fhand.style.rotate = "-3deg";
    };
    place();
    watchRO(place).observe(demoFsrs);
    undo.push(() => {
      fhand.style.left = "";
      fhand.style.top = "";
      fhand.style.rotate = "";
    });
  }

  /* ---------- hero: parallax and "off screen" switch ---------- */
  if (!reduce && hero) {
    let raf = 0;
    listen(
      window,
      "scroll",
      () => {
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          const p = Math.min(1, scrollY / Math.max(1, innerHeight));
          hero.style.setProperty("--sy", p.toFixed(3));
          hero.style.setProperty("--rot", (p * 24).toFixed(2));
        });
      },
      { passive: true },
    );
    undo.push(() => raf && cancelAnimationFrame(raf));
    const watch = watchIO((es) => es.forEach((e) => e.target.classList.toggle("off", !e.isIntersecting)), { rootMargin: "80px" });
    watch.observe(hero);
    feats.forEach((t) => watch.observe(t));
  }

  /* helper: run an async script over and over while its section is visible and not paused */
  const loopIn = (sec: El | null, fn: (ready: Ready) => Promise<void>, gap = 1200) => {
    if (!sec) return;
    let started = false;
    const ready: Ready = () => alive && scrolled && running() && !sec.classList.contains("off") && sec.classList.contains("in");
    const go = async () => {
      while (alive) {
        while (!ready()) await sleep(350);
        await fn(ready);
        await sleep(gap);
      }
    };
    const io = watchIO(
      (es) => {
        if (es[0].isIntersecting && !started) {
          started = true;
          void go();
          io.disconnect();
        }
      },
      { threshold: 0.3 },
    );
    io.observe(sec);
  };

  /* ================= 1. knowledge graph (Obsidian style) ================= */
  const stage = $1("[data-graph]");
  if (stage) startGraph(stage);

  /** Label text in at most two lines (split at the space nearest the middle), never cut with an ellipsis. */
  function labelLines(name: string): string[] {
    if (name.length <= 12 || !name.includes(" ")) return [name];
    let best = -1;
    for (let i = 0; i < name.length; i++) if (name[i] === " " && (best < 0 || Math.abs(i - name.length / 2) < Math.abs(best - name.length / 2))) best = i;
    return [name.slice(0, best), name.slice(best + 1)];
  }
  function startGraph(stageEl: El) {
    const svg = $1(".gsvg", stageEl) as unknown as Svg;
    const tip = $1(".gtip", stageEl) as El;
    type Node = {
      id: string; name: string; tip?: string; hub: boolean; r: number; accent: string; degree: number; hubOf?: number;
      x: number; y: number; vx: number; vy: number; fx: number; fy: number; hx?: number; hy?: number; g: Svg;
    };
    const base = (n: Omit<Node, "x" | "y" | "vx" | "vy" | "fx" | "fy" | "g">) => ({ ...n, x: 0, y: 0, vx: 0, vy: 0, fx: 0, fy: 0, g: null as unknown as Svg });
    const model = graphModel();
    const nodes: Node[] = model.nodes.map((n) => base(n));
    const links = model.links;
    let W = 0;
    let H = 0;
    const lines: Svg[] = [];
    const dots: Svg[] = [];
    const labs: Svg[] = [];
    const gl = mk("g", {}, svg);
    const gn = mk("g", {}, svg);
    links.forEach(() => lines.push(mk("line", { class: "e" }, gl)));
    nodes.forEach((n) => {
      const g = mk("g", { class: "n" + (n.hub ? " hub" : "") + (n.accent ? " acc-" + n.accent : "") + (n.hub || n.degree >= 5 ? " big" : ""), tabindex: "0", role: "button", "aria-label": n.name + (n.tip ? ". " + n.tip : "") }, gn);
      mk("circle", { class: "hit", r: Math.max(14, n.r + 6) }, g);
      dots.push(mk("circle", { class: "dot", r: 0 }, g));
      const lab = mk("text", { class: "lb", y: n.r + 11, "text-anchor": "middle" }, g);
      const ls = labelLines(n.name);
      ls.forEach((t, li) => {
        const sp = mk("tspan", { x: 0, dy: li ? 11 : 0 }, lab);
        sp.textContent = t;
      });
      labs.push(lab);
      n.g = g;
    });
    undo.push(() => {
      gl.remove();
      gn.remove();
      svg.removeAttribute("viewBox");
      tip.hidden = true;
      tip.replaceChildren();
      svg.classList.remove("focus");
    });
    let alpha = 1;
    let grow = 0;
    let drag: Node | null = null;
    let t0 = 0;
    let active = false;
    let raf = 0;
    let inited = false;
    let hover: Node | null = null;
    const size = () => {
      const r = stageEl.getBoundingClientRect();
      W = r.width;
      H = r.height;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    };
    const place = (spread: number) =>
      nodes.forEach((n, i) => {
        const a = (i / nodes.length) * Math.PI * 2 * 3.1 + i;
        const rr = spread * Math.min(W, H) * (n.hub ? 0.1 : 0.3) * (0.4 + (i % 5) / 5);
        n.x = W / 2 + Math.cos(a) * rr;
        n.y = H / 2 + Math.sin(a) * rr;
        n.vx = n.vy = 0;
      });
    const tick = (t: number) => {
      const S = Math.min(W, H);
      const k = 24 * (S / 600);
      const L = S * 0.095;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.fx = (W / 2 - a.x) * 0.002;
        a.fy = (H / 2 - a.y) * 0.002;
        if (a.hx !== undefined && a.hy !== undefined) {
          a.fx += (a.hx - a.x) * 0.06;
          a.fy += (a.hy - a.y) * 0.06;
        }
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d = Math.sqrt(dx * dx + dy * dy + 0.5);
          const f = (k * (a.hub && b.hub ? 3 : a.hub || b.hub ? 1.4 : 1)) / Math.max(d, 14) / d;
          a.fx += dx * f;
          a.fy += dy * f;
          b.fx -= dx * f;
          b.fy -= dy * f;
          const minD = S * 0.05 + a.r + b.r;
          if (d < minD) {
            const push = ((minD - d) * 0.06) / d;
            a.fx += dx * push;
            a.fy += dy * push;
            b.fx -= dx * push;
            b.fy -= dy * push;
          }
        }
      }
      links.forEach((l) => {
        const a = nodes[l.a];
        const b = nodes[l.b];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const rest = l.own ? L : L * 1.5;
        const f = (d - rest) * (l.own ? 0.0012 : 0.0003);
        a.fx += (dx / d) * f;
        a.fy += (dy / d) * f;
        b.fx -= (dx / d) * f;
        b.fy -= (dy / d) * f;
      });
      nodes.forEach((n, i) => {
        if (n === drag) {
          n.vx = n.vy = 0;
          return;
        }
        const idle = running() ? 0.004 : 0; /* barely breathing: the map stays where it was put */
        n.vx = (n.vx + n.fx * alpha + Math.sin(t / 1400 + i * 1.7) * idle) * 0.82;
        n.vy = (n.vy + n.fy * alpha + Math.cos(t / 1600 + i * 2.3) * idle) * 0.82;
        n.x = Math.max(28, Math.min(W - 28, n.x + n.vx));
        n.y = Math.max(28, Math.min(H - 28, n.y + n.vy));
      });
    };
    const linked = (n: Node) => {
      const s = new Set([n]);
      links.forEach((l) => {
        if (nodes[l.a] === n) s.add(nodes[l.b]);
        if (nodes[l.b] === n) s.add(nodes[l.a]);
      });
      return s;
    };
    const placeTip = (n: Node) => {
      const x = Math.min(W - tip.offsetWidth - 12, Math.max(12, n.x + 14));
      const y = Math.min(H - tip.offsetHeight - 12, Math.max(12, n.y - tip.offsetHeight - 10));
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    };
    const draw = () => {
      links.forEach((l, i) => {
        const a = nodes[l.a];
        const b = nodes[l.b];
        const e = lines[i];
        e.setAttribute("x1", String(a.x));
        e.setAttribute("y1", String(a.y));
        e.setAttribute("x2", String(b.x));
        e.setAttribute("y2", String(b.y));
        e.style.opacity = String(Math.min(1, grow * 1.4));
      });
      nodes.forEach((n, i) => {
        const gr = Math.max(0, Math.min(1, grow * 1.6 - (i / nodes.length) * 0.6));
        const e = 1 - Math.pow(1 - gr, 3);
        const sc = e * (1 + 0.15 * Math.sin(gr * Math.PI));
        n.g.setAttribute("transform", `translate(${n.x.toFixed(1)} ${n.y.toFixed(1)})`);
        dots[i].setAttribute("r", (n.r * sc).toFixed(2));
        labs[i].style.setProperty("--lo", String(Math.max(0, (gr - 0.4) / 0.6).toFixed(2)));
      });
      if (hover) placeTip(hover);
    };
    const frame = (t: number) => {
      raf = 0;
      if (!alive) return;
      if (!t0) t0 = t;
      if (grow < 1) grow = Math.min(1, (t - t0) / 1800);
      alpha = Math.max(0.05, alpha * 0.992);
      if (drag) alpha = Math.max(alpha, 0.5);
      if (drag || grow < 1) tick(t);
      if (grow >= 1 && !declutterDone) {
        declutterDone = true;
        declutter(); /* the bloom ends on a map whose labels never overlap */
      }
      draw();
      const want = active && (running() || drag);
      if (want || grow < 1) raf = requestAnimationFrame(frame);
    };
    const kick = () => {
      if (!raf && alive) raf = requestAnimationFrame(frame);
    };
    undo.push(() => raf && cancelAnimationFrame(raf));
    const layout = graphLayout(nodes);
    const homes = () => {
      const R = Math.min(W, H) * 0.5;
      const rx = R; /* round, not stretched: the cluster is a disc */
      nodes.forEach((n, i) => {
        n.hx = W / 2 + layout[i].x * rx;
        n.hy = H / 2 + layout[i].y * R;
        n.x = n.hx;
        n.y = n.hy;
        n.vx = n.vy = 0;
      });
    };
    let declutterDone = false;
    const declutter = () => {
      /* deterministic label pass: push apart nodes whose label boxes (or dots) would overlap */
      const box = (n: Node) => {
        const ls = labelLines(n.name);
        const w = Math.max(...ls.map((t) => t.length)) * 5.8 + 10;
        return { l: n.x - Math.max(w / 2, n.r), r: n.x + Math.max(w / 2, n.r), t: n.y - n.r, b: n.y + n.r + 4 + ls.length * 11 };
      };
      for (let it = 0; it < 500; it++) {
        let moved = false;
        for (let i = 0; i < nodes.length; i++)
          for (let j = i + 1; j < nodes.length; j++) {
            const A = box(nodes[i]);
            const B = box(nodes[j]);
            const ox = Math.min(A.r, B.r) - Math.max(A.l, B.l);
            const oy = Math.min(A.b, B.b) - Math.max(A.t, B.t);
            if (ox <= 0 || oy <= 0) continue;
            moved = true;
            const a = nodes[i];
            const b = nodes[j];
            if (oy < ox) {
              const s = a.y <= b.y ? 1 : -1;
              a.y -= (s * (oy + 1)) / 2;
              b.y += (s * (oy + 1)) / 2;
            } else {
              const s = a.x <= b.x ? 1 : -1;
              a.x -= (s * (ox + 1)) / 2;
              b.x += (s * (ox + 1)) / 2;
            }
          }
        nodes.forEach((n) => {
          n.x = Math.max(40, Math.min(W - 40, n.x));
          n.y = Math.max(24, Math.min(H - 34, n.y));
        });
        if (!moved) break;
      }
    };
    const settle = () => {
      homes();
      for (let i = 0; i < 160; i++) {
        alpha = 0.4;
        tick(i * 16);
      }
      declutter();
      alpha = 0.05;
      grow = 1;
      declutterDone = true;
      nodes.forEach((n) => {
        n.hx = n.x;
        n.hy = n.y;
      });
      draw();
    };
    const init = () => {
      if (inited) return;
      size();
      if (W < 50) return;
      inited = true;
      settle();
    };
    let bloomed = false;
    const bloom = () => {
      if (bloomed || reduce || !scrolled) return;
      bloomed = true;
      declutterDone = false;
      place(0.06);
      alpha = 1;
      grow = 0;
      t0 = 0;
      active = true;
      kick();
    };
    watchRO(() => {
      if (!inited) {
        init();
        return;
      }
      const r = stageEl.getBoundingClientRect();
      if (r.width < 50 || r.height < 50 || (Math.abs(r.width - W) < 2 && Math.abs(r.height - H) < 2)) return;
      const ow = W;
      const oh = H;
      size();
      nodes.forEach((n) => {
        n.x = (n.x / ow) * W;
        n.y = (n.y / oh) * H;
        n.hx = ((n.hx ?? n.x) / ow) * W;
        n.hy = ((n.hy ?? n.y) / oh) * H;
      });
      draw();
    }).observe(stageEl);
    watchIO(
      (es) => {
        active = es[0].isIntersecting;
        if (active) {
          init();
          bloom();
          kick();
        }
      },
      { threshold: 0.25 },
    ).observe(stageEl);
    const iv = setInterval(() => {
      if (active && running() && !raf) kick();
    }, 700);
    undo.push(() => clearInterval(iv));
    /* the label: only on hover / focus */
    const showTip = (n: Node) => {
      hover = n;
      tip.hidden = false;
      const b = document.createElement("b");
      b.textContent = n.name;
      tip.replaceChildren(b, document.createTextNode(n.hub ? "Môn học" : n.tip || ""));
      placeTip(n);
      const near = linked(n);
      svg.classList.add("focus");
      links.forEach((l, i) => lines[i].classList.toggle("hot", nodes[l.a] === n || nodes[l.b] === n));
      nodes.forEach((m) => m.g.classList.toggle("lit", near.has(m)));
    };
    const hideTip = () => {
      hover = null;
      tip.hidden = true;
      svg.classList.remove("focus");
      lines.forEach((e) => e.classList.remove("hot"));
      nodes.forEach((m) => m.g.classList.remove("lit"));
    };
    nodes.forEach((n) => {
      const g = n.g;
      g.addEventListener("pointerenter", () => showTip(n));
      g.addEventListener("pointerleave", () => {
        if (!drag) hideTip();
      });
      g.addEventListener("focus", () => showTip(n));
      g.addEventListener("blur", hideTip);
      g.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter" || (e as KeyboardEvent).key === " ") {
          e.preventDefault();
          showTip(n);
        }
      });
      g.addEventListener("pointerdown", (e) => {
        drag = n;
        g.setPointerCapture((e as PointerEvent).pointerId);
        e.preventDefault();
        showTip(n);
        kick();
      });
      g.addEventListener("pointermove", (e) => {
        if (drag !== n) return;
        const r = stageEl.getBoundingClientRect();
        n.x = Math.max(20, Math.min(W - 20, (e as PointerEvent).clientX - r.left));
        n.y = Math.max(20, Math.min(H - 20, (e as PointerEvent).clientY - r.top));
        showTip(n);
        kick();
      });
      const up = () => {
        if (drag === n) {
          drag = null;
          alpha = 0.7;
          kick();
        }
      };
      g.addEventListener("pointerup", up);
      g.addEventListener("pointercancel", up);
    });
    listen(stageEl, "pointerdown", (e: PointerEvent) => {
      if (!(e.target as Element).closest(".n")) hideTip();
    });
  }

  /* ================= 2. outline ================= */
  (() => {
    const sec = $1("#de-cuong");
    const demo = $1("[data-out]");
    if (!demo) return;
    const heads = $("[data-h]", demo);
    const lis = $("[data-t]", demo);
    const scan = $1(".scan", demo) as El;
    const page = $1(".pdf-page", demo) as El;
    const chat = $1("[data-chat2]", demo) as El;
    const text = chat.textContent ?? "";
    const l5 = $1('[data-t="5"]', demo) as El;
    undo.push(() => {
      lis.forEach((l) => l.classList.remove("h", "pulse"));
      heads.forEach((h) => h.classList.remove("hit"));
      chat.textContent = text;
      chat.removeAttribute("data-caret");
    });
    const hide = () => {
      lis.forEach((l) => l.classList.add("h"));
      heads.forEach((h) => h.classList.remove("hit"));
      chat.textContent = "";
      lis.forEach((l) => l.classList.remove("pulse"));
    };
    if (reduce) return;
    loopIn(
      sec,
      async (ready) => {
        hide();
        await sleep(500);
        const Hh = page.clientHeight;
        const anim = scan.animate([{ transform: "translateY(-100%)" }, { transform: `translateY(${Hh}px)` }], { duration: 3800, easing: "linear", fill: "forwards" });
        const seen = new Set<number>();
        const iv = setInterval(() => {
          heads.forEach((h, i) => {
            if (!seen.has(i) && h.getBoundingClientRect().top < scan.getBoundingClientRect().bottom) {
              seen.add(i);
              h.classList.add("hit");
              $1(`[data-t="${i}"]`, demo)?.classList.remove("h");
            }
          });
        }, 60);
        undo.push(() => clearInterval(iv));
        await anim.finished.catch(() => {});
        clearInterval(iv);
        lis.forEach((l) => l.classList.remove("h"));
        await sleep(500);
        chat.setAttribute("data-caret", "1");
        for (const ch of text) {
          while (!ready()) await sleep(300);
          chat.textContent += ch;
          await sleep(55);
        }
        chat.removeAttribute("data-caret");
        await sleep(400);
        l5.classList.add("pulse");
        await sleep(3000);
      },
      800,
    );
  })();

  /* ================= 3. card ================= */
  (() => {
    const sec = $1("#the-nguon");
    const demo = $1("[data-card]");
    if (!demo) return;
    const code = $1("[data-md]", demo) as El;
    const rc = $1(".rcard", demo) as El;
    const kids: Record<number, Array<El | null>> = {
      0: [$1(".rc-meta", rc), $1("h3", rc)],
      2: [$1("ul", rc)],
      3: [$1(".rc-f", rc)],
      4: [$1(".src-b", rc), $1(".src-pop", rc)],
    };
    const all = Object.values(kids).flat().filter((e): e is El => !!e);
    undo.push(() => {
      all.forEach((e) => e.classList.remove("h"));
      code.removeAttribute("data-caret");
      code.textContent = MD_LINES.join("\n");
    });
    code.textContent = MD_LINES.join("\n");
    if (reduce) return;
    loopIn(
      sec,
      async (ready) => {
        code.textContent = "";
        all.forEach((e) => e.classList.add("h"));
        code.setAttribute("data-caret", "1");
        await sleep(500);
        for (let i = 0; i < MD_LINES.length; i++) {
          for (const ch of MD_LINES[i] + (i < MD_LINES.length - 1 ? "\n" : "")) {
            while (!ready()) await sleep(300);
            code.textContent += ch;
            await sleep(22);
          }
          (kids[i] || []).forEach((e) => e?.classList.remove("h"));
          await sleep(250);
        }
        code.removeAttribute("data-caret");
        await sleep(5200);
      },
      600,
    );
  })();

  /* ================= 4. FSRS (the curve itself is drawn by the server: landing.tsx / fsrs-curve.ts) ================= */
  (() => {
    const sec = $1("#lich-on");
    const demo = $1("[data-fsrs]");
    if (!demo) return;
    const line = $1(".c-line", demo) as unknown as Svg;
    const dc = $("circle", $1(".c-dots", demo) as El) as unknown as Svg[];
    const qcs = $("[data-q]", demo);
    const WIDTH = 900;
    const xs = dc.map((c) => Number(c.getAttribute("cx")));
    undo.push(() => {
      dc.forEach((c) => {
        c.style.opacity = "";
        c.style.transformBox = "";
        c.style.transformOrigin = "";
      });
      qcs.forEach((q) => (q.style.opacity = ""));
    });
    if (reduce) return;
    loopIn(
      sec,
      async () => {
        dc.forEach((c) => (c.style.opacity = "0.15"));
        qcs.forEach((q) => (q.style.opacity = "0.15"));
        const a = line.animate([{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: 4200, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" });
        xs.forEach((x, i) =>
          void sleep((x / WIDTH) * 4200).then(() => {
            const c = dc[i];
            c.style.opacity = "1";
            c.animate([{ transform: "scale(0)" }, { transform: "scale(1.4)" }, { transform: "scale(1)" }], { duration: 450, easing: "ease-out" });
            c.style.transformBox = "fill-box";
            c.style.transformOrigin = "center";
          }),
        );
        await sleep(900);
        for (const q of qcs) {
          q.style.opacity = "1";
          q.animate([{ transform: "translate(-40px,0)", opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 650, easing: "cubic-bezier(.3,1.35,.5,1)" });
          await sleep(220);
        }
        await a.finished.catch(() => {});
        await sleep(4200);
      },
      500,
    );
  })();

  /* ================= 5. practice ================= */
  (() => {
    const sec = $1("#luyen-de");
    const demo = $1("[data-prac]");
    if (!demo) return;
    const pool = $1(".pool", demo) as El;
    const srcs = $(".qt", pool);
    const slots = $(".slot", demo);
    const fins = srcs.map((q) => {
      const f = q.cloneNode(true) as El;
      f.classList.add("fin");
      slots[Number(q.dataset.to)].appendChild(f);
      q.classList.add("src");
      return f;
    });
    const msg = document.createElement("p");
    msg.className = "pool-msg";
    msg.textContent = "Đã gom 5 câu hỏi theo dạng, câu tính toán đứng đầu.";
    pool.appendChild(msg);
    undo.push(() => {
      fins.forEach((f) => f.remove());
      msg.remove();
      srcs.forEach((q) => {
        q.classList.remove("src");
        q.style.visibility = "";
        q.style.transform = "";
      });
    });
    if (reduce) return;
    loopIn(
      sec,
      async (ready) => {
        fins.forEach((f) => (f.style.visibility = "hidden"));
        srcs.forEach((q) => {
          q.style.visibility = "visible";
          q.style.transform = "";
        });
        msg.style.visibility = "hidden";
        await sleep(900);
        for (let i = 0; i < srcs.length; i++) {
          while (!ready()) await sleep(300);
          const q = srcs[i];
          const f = fins[i];
          const a = q.getBoundingClientRect();
          const b = f.getBoundingClientRect();
          const an = q.animate([{ transform: "none" }, { transform: `translate(${b.left - a.left}px,${b.top - a.top}px)` }], { duration: 700, easing: "cubic-bezier(.3,1.35,.5,1)", fill: "forwards" });
          await an.finished.catch(() => {});
          f.style.visibility = "visible";
          q.style.visibility = "hidden";
          an.cancel();
          await sleep(150);
        }
        msg.style.visibility = "visible";
        await sleep(5000);
      },
      400,
    );
  })();

  /* ================= 6. natural-language edit ================= */
  (() => {
    const sec = $1("#chinh-sua");
    const demo = $1("[data-nl]");
    if (!demo) return;
    const inp = $1("[data-nl-text]", demo) as El;
    const diff = $1("[data-diff]", demo) as El;
    const st = $1("[data-st]", demo) as El;
    const row = $1(".target", demo) as El;
    const dl = $1(".dl", demo) as El;
    const applyBtn = $1("[data-apply]", demo) as HTMLButtonElement;
    const undoBtn = $1("[data-undo]", demo) as HTMLButtonElement;
    const text = inp.textContent ?? "";
    snap(inp);
    const stHtml = st.outerHTML;
    const rowWasOn = row.classList.contains("on");
    const diffWasOn = diff.classList.contains("on");
    undo.push(() => {
      st.className = $1("[data-st]", demo) === st ? st.className : "";
      row.classList.toggle("on", rowWasOn);
      diff.classList.toggle("on", diffWasOn);
      dl.innerHTML = DIFF_TEXT;
      void stHtml;
    });
    const toDone = () => {
      st.className = "st done";
      st.textContent = "Đã học";
      row.classList.remove("on");
    };
    const toTodo = () => {
      st.className = "st todo";
      st.textContent = "Chưa học";
      row.classList.add("on");
    };
    const showDiff = () => {
      diff.classList.add("on");
      row.classList.add("on");
    };
    const stText = st.textContent;
    const stClass = st.className;
    undo.push(() => {
      st.className = stClass;
      st.textContent = stText;
    });
    listen(applyBtn, "click", () => {
      toDone();
      row.animate([{ transform: "scale(1.02)" }, { transform: "none" }], { duration: 400, easing: "ease-out" });
      dl.textContent = "Đã áp dụng cho mục 2.1 · Hiệu ứng Mpemba. Bấm Hoàn tác nếu muốn quay lại.";
    });
    listen(undoBtn, "click", () => {
      toTodo();
      setDiffLine(dl);
    });
    if (reduce) {
      showDiff();
      return;
    }
    loopIn(
      sec,
      async (ready) => {
        inp.textContent = "";
        diff.classList.remove("on");
        toTodo();
        row.classList.remove("on");
        setDiffLine(dl);
        await sleep(500);
        inp.setAttribute("data-caret", "1");
        for (const ch of text) {
          while (!ready()) await sleep(300);
          inp.textContent += ch;
          await sleep(55);
        }
        inp.removeAttribute("data-caret");
        await sleep(500);
        showDiff();
        await sleep(1500);
        applyBtn.click();
        await sleep(2600);
        undoBtn.click();
        await sleep(2200);
      },
      600,
    );
  })();

  /* ---------- try ---------- */
  const tryBox = $1("[data-try]");
  const gradeBtn = tryBox ? $1("[data-grade]", tryBox) : null;
  if (tryBox && gradeBtn) {
    listen(gradeBtn, "click", () => {
      const r = $1("[data-result]", tryBox);
      if (!reduce) r?.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 500, easing: "cubic-bezier(.16,1,.3,1)" });
    });
  }

  /* ---------- footer: ESSITY rises with a delay once the footer is reached ---------- */
  if (end) {
    if (reduce) end.classList.add("wm-in");
    else {
      const io = watchIO(
        (es) => {
          if (es[0].isIntersecting) {
            end.classList.add("wm-in");
            io.disconnect();
          }
        },
        { threshold: 0.4 },
      );
      io.observe(end);
    }
  }

  return () => {
    alive = false;
    timers.forEach(clearTimeout);
    timers.clear();
    undo.splice(0).reverse().forEach((f) => f());
  };
}

/** The "preview" line of the natural-language demo: kept as DOM, never parsed from a string. */
function setDiffLine(dl: Element) {
  dl.replaceChildren();
  dl.append("Mục 2.1 · Hiệu ứng Mpemba: ");
  const s = document.createElement("s");
  s.textContent = "Chưa học";
  const b = document.createElement("strong");
  b.textContent = "Đã học";
  dl.append(s, " → ", b);
}
