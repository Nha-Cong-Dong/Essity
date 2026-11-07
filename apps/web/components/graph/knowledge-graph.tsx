"use client";

import cytoscape, { type Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";

import { shortLabel } from "@/lib/graph";
import { settleLabels } from "@/lib/graph-labels";
import { INITIAL_ZOOM_STEP, multiStylesheet } from "@/lib/graph-multi-style";
import { optionsFor, seededRandom, type SimEdge, type SimNode, spiralStart, stepSim } from "@/lib/graph-sim";
import { type MultiCard, type SubjectGraph, v4Highlights } from "@/lib/graph-multi";
import { buildTopicGraph, tint } from "@/lib/graph-topic";

import { DetailCard, GraphEmpty, GraphLegend, ZoomControls } from "./graph-overlays";

// V16/V17: the knowledge graph of one or several subjects. Nodes are cards coloured by subject,
// edges are the links between cards. GRAPH-V4-CANVAS: the canvas fills the page beside the rail; a
// floating legend (top left), zoom buttons (bottom left) and a detail card (right; a bottom sheet on a
// phone) sit on it, as in .work/DESIGN-V4/mockups/graph.html.

let registered = false;
const MAX_FIT_ZOOM = 1.5;
const SETTLE_STEPS = 220; // fixed, not time-based (E-10)
// Full-bleed inside AppShell's <main>: negative margins cancel its gutter and padding, and the height
// is the window minus the phone's top bar (56) and tab bar (56 + safe area).
const FRAME =
  "relative -mx-(--page-gutter) -mt-6 -mb-4 h-[calc(100dvh-112px-env(safe-area-inset-bottom))] min-h-80 overflow-hidden bg-bg min-[1024px]:-mt-10 min-[1024px]:-mb-24 min-[1024px]:h-dvh";

export function KnowledgeGraph({
  graphs,
  height,
  focusSubject = null,
}: {
  graphs: SubjectGraph[];
  /** Overrides the full-window height (previews). */
  height?: string;
  focusSubject?: string | null;
}) {
  // GRAPH-LANDING-STYLE: a hub per topic (a subject; a chapter when one subject is focused), ring nodes tinted by topic.
  const model = useMemo(() => buildTopicGraph(graphs, focusSubject), [graphs, focusSubject]);
  const cards = useMemo(() => model.nodes.flatMap((n) => (n.card ? [n.card] : [])), [model]);
  const merged = useMemo(() => ({ cards, topics: model.topics }), [cards, model]);
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  // Q24: the full title of the node under the pointer; the node's own label is cut at 24 characters.
  const [tip, setTip] = useState<{ title: string; x: number; y: number } | null>(null);
  const byTopic = useMemo(() => new Map(model.topics.map((t) => [t.id, t] as const)), [model]);
  const picked = merged.cards.find((c) => c.id === pickedId) ?? null;

  useEffect(() => {
    if (merged.cards.length === 0 || !host.current) return;
    if (!registered) {
      cytoscape.use(fcose);
      registered = true;
    }
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue("--ink").trim() || "#26141d";
    const line = css.getPropertyValue("--line-strong").trim() || "#8f6676";
    const hong = css.getPropertyValue("--hong").trim() || "#d1347a";
    const now = css.getPropertyValue("--now").trim() || "#891b4c";
    const sheet = css.getPropertyValue("--sheet").trim() || "#ffffff";
    const soft = css.getPropertyValue("--ink-soft").trim() || ink;
    const display = css.getPropertyValue("--font-display").trim() || "sans-serif";
    const cy = cytoscape({
      container: host.current,
      elements: [
        ...model.nodes.map((n, i) => {
          const color = byTopic.get(n.topicId)?.color ?? ink;
          return {
            position: spiralStart(i),
            classes: n.hub ? "hub" : "card",
            data: {
              id: n.id,
              label: n.hub ? n.label : shortLabel(n.label),
              full: n.full,
              color,
              fill: tint(color, sheet, n.hub ? 0.5 : 0.3),
              topic: n.topicId,
              size: n.size,
            },
          };
        }),
        ...model.edges.map((e) => ({ data: { id: e.id, source: e.from, target: e.to } })),
      ],
      style: [...multiStylesheet(ink, line, sheet, soft, display, css.getPropertyValue("--bg").trim() || sheet), ...v4Highlights(ink, hong, now)],
      minZoom: 0.2,
      maxZoom: 3,
      boxSelectionEnabled: false,
    });
    cyRef.current = cy;
    // The design-preview route (it always has ?state=) lets e2e read node positions to drag them.
    if (new URLSearchParams(window.location.search).has("state")) {
      (host.current as HTMLDivElement & { __cy?: cytoscape.Core }).__cy = cy;
    }
    // Labels appear once the reader is zoomed in far enough to read them; a hovered node always shows its own.
    // Like the subject graph, the labels are always on (they are cut at 24 characters).
    cy.nodes().addClass("labelled");
    cy.on("tap", "node.card", (ev) => setPickedId(ev.target.id()));
    // Hover lights a node and its neighbours; the rest dims (Obsidian-style).
    const showTip = (ev: cytoscape.EventObject) => {
      const p = ev.target.renderedPosition();
      setTip({ title: String(ev.target.data("full")), x: p.x, y: p.y });
    };
    cy.on("mouseover", "node", showTip);
    cy.on("drag zoom pan", () => setTip(null));
    cy.on("mouseover", "node", (ev) => {
      const hood = ev.target.closedNeighborhood();
      cy.elements().not(hood).addClass("dim");
      hood.addClass("hot");
    });
    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dim hot");
      setTip(null);
    });
    // UI-A: fit puts the whole graph in the middle; a graph of a few cards is not blown up, so its
    // labels keep their size and the canvas does not look empty at the edges.
    const layout = cy.layout({
      name: "fcose",
      animate: false,
      randomize: false, // start from the fixed spiral above: the same cards give the same picture on every load
      fit: true,
      padding: 56,
      nodeDimensionsIncludeLabels: false,
      idealEdgeLength: 90,
      nodeRepulsion: 6500,
    } as cytoscape.LayoutOptions);
    layout.one("layoutstop", () => {
      if (cy.zoom() > MAX_FIT_ZOOM) {
        cy.zoom(MAX_FIT_ZOOM);
        cy.center();
      }
    });
    layout.run();
    // Float: after the first layout the nodes keep drifting under a small force simulation (springs on
    // the edges, repulsion, a pull to the middle). A dragged node is pinned under the pointer and the
    // rest follow. Reduced motion: no drift; nodes can still be dragged.
    let frame = 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startSim = () => {
      if (reduced) return;
      const list = cy.nodes().toArray();
      const index = new Map(list.map((n, i) => [n.id(), i] as const));
      const sim: SimNode[] = list.map((n) => ({ id: n.id(), x: n.position("x"), y: n.position("y"), vx: 0, vy: 0, pinned: false, group: String(n.data("topic")) }));
      const links: SimEdge[] = cy
        .edges()
        .toArray()
        .flatMap((e) => {
          const a = index.get(e.source().id());
          const b = index.get(e.target().id());
          return a === undefined || b === undefined ? [] : [{ a, b }];
        });
      cy.on("grab", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) sim[i].pinned = true;
      });
      cy.on("drag", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) {
          sim[i].x = ev.target.position("x");
          sim[i].y = ev.target.position("y");
        }
      });
      cy.on("free", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) sim[i].pinned = false;
      });
      const opts = optionsFor(list.length);
      const noise = seededRandom(1);
      let alpha = 0.5;
      let calm = 0; // frames spent at the floor; the loop stops after ~10 s and wakes on touch or hover
      let running = false;
      const wake = () => {
        calm = 0;
        alpha = Math.max(alpha, 0.3);
        if (!running) {
          running = true;
          frame = requestAnimationFrame(tick);
        }
      };
      const tick = () => {
        alpha = Math.max(0.1, alpha * 0.995);
        if (alpha <= 0.1 && ++calm > 600) {
          running = false;
          return;
        }
        stepSim(sim, links, alpha, noise, opts);
        cy.batch(() => {
          list.forEach((n, i) => {
            if (!sim[i].pinned) n.position({ x: sim[i].x, y: sim[i].y });
          });
        });
        frame = requestAnimationFrame(tick);
      };
      // E-10: the picture must not depend on when it is looked at. Settle a fixed number of steps now
      // (seeded noise, so the same cards give the same positions), push overlapping labels apart once,
      // and frame it. The loop only wakes when the reader grabs a node.
      for (let s = 0; s < SETTLE_STEPS; s++) stepSim(sim, links, Math.max(0.1, 0.5 * 0.995 ** s), noise, opts);
      cy.batch(() => {
        list.forEach((n, i) => n.position({ x: sim[i].x, y: sim[i].y }));
      });
      settleLabels(cy);
      list.forEach((n, i) => {
        sim[i].x = n.position("x");
        sim[i].y = n.position("y");
      });
      cy.fit(cy.nodes(), 48);
      if (cy.zoom() > MAX_FIT_ZOOM) {
        cy.zoom(MAX_FIT_ZOOM);
        cy.center();
      }
      // UI-NITS-0811: the first view opens one zoom step further out (the Fit button still fits).
      cy.zoom({ level: cy.zoom() / INITIAL_ZOOM_STEP, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
      cy.on("grab", "node", wake);
    };
    startSim(); // the layout is synchronous (animate: false), so the nodes are already placed
    const resize = new ResizeObserver(() => cy.resize());
    resize.observe(host.current);
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [model, byTopic, merged.cards.length]);

  // The card being read stands out in the graph.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("picked");
    if (pickedId) cy.getElementById(pickedId).addClass("picked");
  }, [pickedId, merged]);

  // The subjects switched off in the chips are not drawn (their edges go with them).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        n.style("display", hidden.has(String(n.data("topic"))) ? "none" : "element");
      });
    });
  }, [hidden]);

  const toggle = (id: string) =>
    setHidden((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const zoomBy = (f: number) => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };
  const fit = () => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.fit(undefined, 48);
    if (cy.zoom() > MAX_FIT_ZOOM) {
      cy.zoom(MAX_FIT_ZOOM);
      cy.center();
    }
  };

  if (merged.cards.length === 0) {
    return (
      <div className={FRAME} style={height ? { height } : undefined}>
        <div className="h-full p-3 min-[1024px]:p-5">
          <GraphEmpty href={graphs[0] ? `/subjects/${graphs[0].id}/sessions/new` : null} />
        </div>
      </div>
    );
  }
  const topicOf = (cardId: string) => byTopic.get(model.nodes.find((n) => n.id === cardId)?.topicId ?? "");
  const topic = picked ? topicOf(picked.id) : undefined;
  // The cards linked to the picked one (either end), for the "Liên quan" chips.
  const related = picked
    ? [...new Set(model.edges.flatMap((e) => (e.from === picked.id ? [e.to] : e.to === picked.id ? [e.from] : [])))]
        .flatMap((id) => {
          const c = merged.cards.find((x) => x.id === id);
          return c ? [{ id: c.id, title: c.title }] : [];
        })
        .slice(0, 8)
    : [];
  return (
    <div className={FRAME} style={height ? { height } : undefined}>
      <div className="absolute inset-0">
      <div
        ref={host}
        role="img"
        aria-label={`Đồ thị tri thức, ${merged.cards.length} thẻ. Duyệt bằng bàn phím ở danh sách thẻ trong chú giải.`}
        data-graph-canvas
        data-foreign-dom
        className="size-full cursor-grab touch-none overflow-hidden active:cursor-grabbing"
      />
      </div>
      {tip && (
        <div
          aria-hidden="true"
          style={{ left: tip.x, top: tip.y }}
          className="pointer-events-none absolute z-10 max-w-64 -translate-x-1/2 -translate-y-[calc(100%+14px)] rounded-control bg-ink px-3 py-2 text-meta text-sheet wrap-anywhere"
        >
          {tip.title}
        </div>
      )}
      <GraphLegend
        topics={model.topics}
        hidden={hidden}
        onToggle={toggle}
        total={merged.cards.length}
        mode={model.mode}
        cardList={model.nodes
          .filter((n) => n.card && !hidden.has(n.topicId))
          .map((n) => n.card as MultiCard)
          .map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => setPickedId(c.id)}
                className="flex min-h-11 w-full items-center gap-2 rounded-control px-1 text-left text-meta hover:bg-sunken"
              >
                <span aria-hidden="true" className="inline-block size-3 shrink-0 rounded-full" style={{ background: topicOf(c.id)?.color }} />
                <span className="wrap-anywhere">{c.title}</span>
              </button>
            </li>
          ))}
      />
      <ZoomControls onIn={() => zoomBy(1.3)} onOut={() => zoomBy(1 / 1.3)} onFit={fit} />
      {picked && topic && (
        <DetailCard card={picked} subject={topic.name} color={topic.color} related={related} onPick={setPickedId} onClose={() => setPickedId(null)} />
      )}
    </div>
  );
}
