import type { StylesheetJson } from "cytoscape";

import { EDGE_KINDS, EDGE_STYLE } from "@/lib/graph";

// T9.10a (DESIGN §6.15): the Cytoscape stylesheet as a pure function of the zoom and the palette,
// so the canvas restyles on zoom and on a theme switch without rebuilding the graph. Ink and
// lines only: no colour outside the palette handed in.
//
// - A card is drawn DOT px but hit as HIT px: its box is HIT/zoom model units with a DOT/HIT
//   circle inside (background-image), so the touch target stays 44 px at any zoom.
// - Strokes keep their pixel width at any zoom (width / zoom); arrows follow the stroke.
// - Outside 2 steps from the selected card (class "far") strokes and dots drop to opacity .5 and
//   nothing else changes; labels are never faded.

export const HIT = 44;
export const DOT = 20;

export type Palette = { ink: string; line: string; sheet: string; focus: string; soft: string };

export function dotImage(p: Palette, selected: boolean): string {
  const shapes = selected
    ? `<circle cx='22' cy='22' r='20' fill='none' stroke='${p.focus}' stroke-width='3'/><circle cx='22' cy='22' r='9.5' fill='${p.sheet}' stroke='${p.ink}' stroke-width='4'/>`
    : `<circle cx='22' cy='22' r='9' fill='${p.sheet}' stroke='${p.ink}' stroke-width='2.5'/>`;
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${HIT}' height='${HIT}' viewBox='0 0 ${HIT} ${HIT}'>${shapes}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

export function graphStylesheet(p: Palette, zoom: number): StylesheetJson {
  const dot = `${(DOT / HIT) * 100}%`;
  const sheet: StylesheetJson = [
    {
      selector: "node.card",
      style: {
        width: HIT / zoom,
        height: HIT / zoom,
        shape: "rectangle",
        "background-opacity": 0,
        "border-width": 0,
        "background-image": dotImage(p, false),
        "background-fit": "none",
        "background-width": dot,
        "background-height": dot,
        "background-clip": "none",
        label: (n: cytoscape.NodeSingular) =>
          zoom >= 1 || n.hasClass("near") || n.hasClass("picked") ? String(n.data("label")) : "",
        color: p.ink,
        "font-size": 13 / zoom,
        "text-valign": "bottom",
        "text-margin-y": 2 / zoom,
        "text-wrap": "ellipsis",
        "text-max-width": `${130 / zoom}px`,
      },
    },
    { selector: "node.card.picked", style: { "background-image": dotImage(p, true) } },
    {
      selector: "node[?isSection]",
      style: {
        shape: "round-rectangle",
        "background-opacity": 0,
        "border-width": 1 / zoom,
        "border-color": p.line,
        label: "data(label)",
        color: p.soft,
        "font-size": 12 / zoom,
        "text-valign": "top",
        "text-halign": "center",
        "text-margin-y": -4 / zoom,
        padding: `${24 / zoom}px`,
      },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": p.ink,
        "target-arrow-color": p.ink,
        "source-arrow-color": p.ink,
        "arrow-scale": 1,
        width: 2 / zoom,
      },
    },
  ];
  for (const kind of EDGE_KINDS) {
    const s = EDGE_STYLE[kind];
    sheet.push({
      selector: `edge.${kind}`,
      style: {
        width: s.width / zoom,
        "line-style": s.dash ? "dashed" : "solid",
        ...(s.dash ? { "line-dash-pattern": s.dash.map((d) => d / zoom), "line-cap": "round" } : {}),
        ...(s.arrow ? { "target-arrow-shape": s.arrow, ...(s.both ? { "source-arrow-shape": s.arrow } : {}) } : {}),
      },
    });
  }
  sheet.push({ selector: "edge.far, node.card.far", style: { opacity: 0.5 } });
  return sheet;
}
