"use client";

import "katex/dist/katex.min.css";

import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

// CARD-MD: a card's Markdown with maths ($...$ inline, $$...$$ block). Safe by construction: raw HTML
// is never parsed (react-markdown without rehype-raw drops it to text), images are not allowed, links
// get rel=noopener and unsafe protocols are cut by react-markdown's URL filter, and KaTeX runs with
// trust off (no \href/\url tricks) and never throws (a bad formula shows as its source).

const KATEX = { strict: "ignore", trust: false, throwOnError: false, output: "htmlAndMathml" } as const;

const components: ComponentProps<typeof ReactMarkdown>["components"] = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer nofollow" />,
};

export default function MarkdownInner({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[[rehypeKatex, KATEX]]}
      disallowedElements={["img", "iframe", "script", "style"]}
      unwrapDisallowed
      components={components}
    >
      {text}
    </ReactMarkdown>
  );
}
