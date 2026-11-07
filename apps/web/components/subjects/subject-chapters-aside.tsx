"use client";

import { useEffect, useRef, useState } from "react";

import type { SyllabusNode } from "@/lib/syllabus/tree";

// Hackathon D3: read-only outline beside the subject page. A leaf is ticked by the system (it is
// studied), never by the learner. "Tùy chỉnh đề cương" leads to the customise screen.

function Row({ node, depth, nextId }: { node: SyllabusNode; depth: number; nextId: string | null }) {
  const leaf = node.children.length === 0;
  const ticked = leaf ? node.done : node.children.every((c) => c.excluded || isTicked(c));
  const next = leaf && nextId !== null && node.id === nextId;
  return (
    <li>
      <div
        className={`flex items-center gap-2.5 rounded-slip py-1.5 text-small break-words ${node.excluded ? "text-ink-soft line-through" : ""} ${leaf ? "" : "font-semibold"} ${next ? "bg-accent-tint pr-2 font-semibold" : ""}`}
        style={{ paddingLeft: `${depth * 12 + (next ? 8 : 0)}px` }}
      >
        {/* A state always has a shape: a tick when studied, a pink ring on the next one, an empty ring otherwise. */}
        <span
          aria-hidden="true"
          data-ticked={ticked ? "true" : "false"}
          className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full ${ticked ? "bg-correct text-on-hong" : next ? "bg-sheet inset-ring-4 inset-ring-hong" : "inset-ring-2 inset-ring-line-strong"}`}
        >
          {ticked ? <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M2 6.5l2.5 2.5L10 3.5" /></svg> : null}
        </span>
        <span className="min-w-0 flex-1">
          {node.title}
          <span className="sr-only">{ticked ? " (đã học)" : next ? " (tiếp theo)" : " (chưa học)"}</span>
        </span>
        {next ? <span aria-hidden="true" className="shrink-0 rounded-full bg-accent-teal px-2.5 py-0.5 text-chip font-semibold text-on-accent-teal">Tiếp theo</span> : null}
      </div>
      {!leaf && (
        <ul className="m-0 list-none p-0">
          {node.children.map((c) => (
            <Row key={c.id} node={c} depth={depth + 1} nextId={nextId} />
          ))}
        </ul>
      )}
    </li>
  );
}

function isTicked(n: SyllabusNode): boolean {
  return n.children.length === 0 ? n.done : n.children.every((c) => c.excluded || isTicked(c));
}

export function SubjectOutlineAside({ nodes, subjectId, nextId = null }: { nodes: SyllabusNode[]; subjectId: string; nextId?: string | null }) {
  // The list is a tab stop only when it really scrolls, so a keyboard user can reach the hidden rows.
  const list = useRef<HTMLUListElement>(null);
  const [overflows, setOverflows] = useState(false);
  useEffect(() => {
    const el = list.current;
    if (!el) return;
    const measure = () => setOverflows(el.scrollHeight > el.clientHeight);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [nodes]);
  return (
    <aside aria-label="Đề cương" className="flex min-w-0 flex-col gap-3 rounded-tile bg-sheet p-5 shadow-sheet min-[901px]:p-6">
      <h2 className="m-0 font-display text-tile">Đề cương</h2>
      <ul
        ref={list}
        // A list that scrolls must take the keyboard; one that fits is not a tab stop.
        tabIndex={overflows ? 0 : undefined}
        aria-label="Các phần của đề cương"
        className="relative m-0 flex max-h-[60vh] list-none flex-col overflow-y-auto pb-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        {nodes.map((n) => (
          <Row key={n.id} node={n} depth={0} nextId={nextId} />
        ))}
      </ul>
      <div className="flex justify-end">
        <a href={`/subjects/${subjectId}/syllabus`} className="inline-flex min-h-11 items-center text-small font-semibold rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
          Tùy chỉnh đề cương
        </a>
      </div>
    </aside>
  );
}
