import type { StylesheetJson } from "cytoscape";

// V16/V17: the Cytoscape stylesheet of the knowledge graph. A node takes its colour from its own
// data (the subject's colour); edges are one ink line.
export function multiStylesheet(ink: string, line: string, surface = "#ffffff"): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: "data(size)",
        height: "data(size)",
        label: "data(label)",
        // Labels show when zoomed in (class .labelled), or on the node under the pointer (.hot).
        "text-opacity": 0,
        color: ink,
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 3,
        "text-wrap": "ellipsis",
        "text-max-width": "110px",
        // UI-A: a label never sits bare on an edge: a soft plate under the words.
        "text-background-color": surface,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "border-width": 2,
        "border-color": surface,
      },
    },
    { selector: "edge", style: { width: 1, "line-color": line, "curve-style": "bezier", opacity: 0.35, "z-index": 0 } },
    { selector: "node", style: { "z-index": 10 } },
    { selector: "node.labelled", style: { "text-opacity": 1 } },
    { selector: "node.hot", style: { "text-opacity": 1 } },
    { selector: ".dim", style: { opacity: 0.18 } },
    { selector: "node.hot", style: { "border-color": ink, "border-width": 3 } },
    { selector: "edge.hot", style: { opacity: 1, "line-color": ink, width: 2 } },
  ];
}
