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
        "border-width": 2,
        "border-color": "#ffffff",
      },
    },
    { selector: "edge", style: { width: 2, "line-color": line, "curve-style": "bezier", opacity: 0.8 } },
  ];
}
