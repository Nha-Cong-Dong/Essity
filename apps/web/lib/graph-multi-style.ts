import type { StylesheetJson } from "cytoscape";

// V16/V17: the Cytoscape stylesheet of the knowledge graph. A node takes its colour from its own
// data (the subject's colour); edges are one ink line.
export function multiStylesheet(ink: string, line: string): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: 26,
        height: 26,
        label: "data(label)",
        color: ink,
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 3,
        "text-wrap": "ellipsis",
        "text-max-width": "110px",
        // UI-A: a label never sits bare on an edge: a soft plate under the words.
        "text-background-color": "#ffffff",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "border-width": 2,
        "border-color": "#ffffff",
      },
    },
    { selector: "edge", style: { width: 1.5, "line-color": line, "curve-style": "bezier", opacity: 0.55, "z-index": 0 } },
    { selector: "node", style: { "z-index": 10 } },
    { selector: ".dim", style: { opacity: 0.18 } },
    { selector: "node.hot", style: { "border-color": ink, "border-width": 3 } },
    { selector: "edge.hot", style: { opacity: 1, "line-color": ink, width: 2 } },
  ];
}
