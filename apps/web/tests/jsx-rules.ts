// Reads JSX with the TypeScript compiler, so a rule sees an element written over several lines
// and one with a nested element in its props (render={<a … />}), which a line scan misses.
import ts from "typescript";

export type JsxProblem = { line: number; text: string };

type Element = ts.JsxOpeningElement | ts.JsxSelfClosingElement;

function attribute(element: Element, name: string): ts.JsxAttribute | undefined {
  return element.attributes.properties.find(
    (p): p is ts.JsxAttribute => ts.isJsxAttribute(p) && p.name.getText() === name,
  );
}

/** The literal text of a string attribute (`className="…"`), or undefined. */
function literal(element: Element, name: string): string | undefined {
  const init = attribute(element, name)?.initializer;
  if (init && ts.isStringLiteral(init)) return init.text;
  return undefined;
}

/** The source of an expression attribute (`disabled={busy}` → "busy"), or undefined. */
function expression(element: Element, name: string): string | undefined {
  const init = attribute(element, name)?.initializer;
  if (init && ts.isJsxExpression(init) && init.expression) return init.expression.getText();
  return undefined;
}

/** Problems with <Button> elements: a height set by class, a busy submit merely disabled. */
export function buttonProblems(source: string, fileName = "x.tsx"): JsxProblem[] {
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const problems: JsxProblem[] = [];
  const visit = (node: ts.Node) => {
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && node.tagName.getText() === "Button") {
      const line = file.getLineAndCharacterOfPosition(node.getStart()).line + 1;
      if (/\bh-\d+\b/.test(literal(node, "className") ?? "")) {
        problems.push({ line, text: "height set by class: use size" });
      }
      if (literal(node, "type") === "submit" && /^busy\b/.test(expression(node, "disabled") ?? "")) {
        problems.push({ line, text: "busy submit only disabled: use pending" });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return problems;
}
